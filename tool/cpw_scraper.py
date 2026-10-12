#!/usr/bin/env python3
"""Gentle, resumable mirror of https://chessprogramming.org for archival purposes.

The wiki content is licensed CC BY-SA 3.0; keep attribution when redistributing.

Design goals:
  * gentle   - one request at a time, a delay with jitter between requests,
               honours Retry-After and backs off on 429/5xx.
  * idempotent / resumable - crawl state lives in a SQLite file next to the
               content; every file is written atomically (tmp + rename), and a
               file already on disk is never downloaded again (its links are
               re-read from disk instead). Interrupt with Ctrl+C and simply
               run the same command again.
  * stdlib only - no third-party dependencies.

Usage:
  python3 cpw_scraper.py crawl            # start or resume
  python3 cpw_scraper.py crawl --max-requests 20
  python3 cpw_scraper.py status
"""

from __future__ import annotations

import argparse
import html.parser
import logging
import os
import posixpath
import random
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = "https://chessprogramming.org"
HOSTS = {"chessprogramming.org", "www.chessprogramming.org"}
SEEDS = ["/", "/Main_Page", "/Special:AllPages", "/search-index.json"]
USER_AGENT = (
    "cpw-archiver/1.0 (archival mirror; "
    "+https://github.com/the-guish/chess-programming-wiki-backup)"
)
DEFAULT_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"

# Path extensions that are served as-is (anything else is treated as a wiki page).
ASSET_EXTS = {
    ".css", ".js", ".json", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".webp", ".bmp", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pdf",
    ".zip", ".txt", ".xml", ".mp3", ".mp4", ".webm", ".pgn", ".gz",
}
# Characters kept verbatim in on-disk names; everything else is %-escaped so
# names are portable (e.g. "Category:Pioneer" -> "Category%3APioneer.html").
FS_SAFE = "/-_.()~,!'+@"
# 52x are Cloudflare's "origin unreachable" family: transient, never a real answer.
RETRYABLE = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 530}
# Give up the run (exit code EXIT_SITE_DOWN) after this many URLs in a row
# exhaust their retries: the site is down, not the URLs.
MAX_CONSECUTIVE_FAILURES = 3
EXIT_SITE_DOWN = 75

log = logging.getLogger("cpw")


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #
def normalize(ref: str, base_url: str) -> str | None:
    """Return a canonical site path for `ref`, or None if it is off-site/unwanted."""
    ref = ref.strip()
    if not ref or ref.startswith(("#", "mailto:", "javascript:", "data:")):
        return None
    parts = urllib.parse.urlsplit(urllib.parse.urljoin(base_url, ref))
    if parts.scheme not in ("http", "https") or parts.hostname not in HOSTS:
        return None
    if parts.query:  # dynamic URLs (edit links, diffs, ...) are not part of the static mirror
        return None
    path = posixpath.normpath(urllib.parse.unquote(parts.path or "/"))
    if not path.startswith("/") or "/../" in path + "/":
        return None
    if parts.path.endswith("/") and path != "/":
        path += "/"
    return urllib.parse.quote(path, safe="/:@!$&'()*+,;=-._~")


def local_candidates(path: str) -> list[str]:
    """Relative file names a site path may be stored under (first = preferred)."""
    raw = urllib.parse.unquote(path)
    if raw.endswith("/"):
        raw += "index.html"
    rel = urllib.parse.quote(raw.lstrip("/"), safe=FS_SAFE)
    if posixpath.splitext(rel)[1].lower() in ASSET_EXTS:
        return [rel, rel + ".html"]
    return [rel + ".html", rel] if not rel.endswith(".html") else [rel]


def local_for(path: str, content_type: str) -> str:
    rel = local_candidates(path)[0]
    is_html = content_type.startswith("text/html")
    if is_html and not rel.endswith(".html"):
        rel += ".html"
    if not is_html and rel.endswith(".html") and not path.endswith(".html"):
        rel = rel[: -len(".html")]
    return rel


# --------------------------------------------------------------------------- #
# Link extraction
# --------------------------------------------------------------------------- #
CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)|@import\s+['"]([^'"]+)['"]""")
JS_PATH_RE = re.compile(r"""["'`](/[^"'`\s]+\.(?:json|js|css|png|svg|gif|jpe?g|woff2?))["'`]""")


class LinkParser(html.parser.HTMLParser):
    URL_ATTRS = {"href", "src", "poster", "data-src"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if not value:
                continue
            if name in self.URL_ATTRS:
                self.links.append(value)
            elif name == "srcset":
                self.links.extend(c.strip().split()[0] for c in value.split(",") if c.strip())
            elif name == "style":
                self.links.extend(a or b for a, b in CSS_URL_RE.findall(value))


def extract_links(data: bytes, rel: str) -> list[str]:
    ext = posixpath.splitext(rel)[1].lower()
    text = data.decode("utf-8", errors="replace")
    if ext == ".html":
        parser = LinkParser()
        parser.feed(text)
        links = parser.links
        for block in re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I):
            links += [a or b for a, b in CSS_URL_RE.findall(block)]
        return links
    if ext == ".css":
        return [a or b for a, b in CSS_URL_RE.findall(text)]
    if ext == ".js":
        return JS_PATH_RE.findall(text)
    return []


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS urls (
    path         TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|done|missing|failed|skipped|offsite
    local        TEXT,
    http_status  INTEGER,
    content_type TEXT,
    attempts     INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    updated_at   REAL
);
CREATE INDEX IF NOT EXISTS urls_status ON urls(status);
"""


class State:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.executescript(SCHEMA)

    def add(self, paths) -> None:
        self.db.executemany(
            "INSERT OR IGNORE INTO urls(path, updated_at) VALUES (?, ?)",
            [(p, time.time()) for p in paths],
        )
        self.db.commit()

    def next_pending(self) -> str | None:
        row = self.db.execute(
            "SELECT path FROM urls WHERE status='pending'"
            # backlink lists can be rebuilt from the pages, so they go last
            " ORDER BY path LIKE '/Special:WhatLinksHere/%', rowid LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def mark(self, path: str, status: str, **fields) -> None:
        fields.update(status=status, updated_at=time.time())
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE urls SET {cols} WHERE path=?", [*fields.values(), path])
        self.db.commit()

    def requeue(self, statuses) -> int:
        q = ",".join("?" * len(statuses))
        cur = self.db.execute(
            f"UPDATE urls SET status='pending' WHERE status IN ({q})"
            " OR (status='missing' AND http_status >= 500)",  # server errors are never final
            statuses)
        self.db.commit()
        return cur.rowcount

    def counts(self) -> dict[str, int]:
        return dict(self.db.execute("SELECT status, COUNT(*) FROM urls GROUP BY status"))


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
class Fetcher:
    def __init__(self, delay: float, jitter: float, max_retries: int, timeout: float) -> None:
        self.delay, self.jitter = delay, jitter
        self.max_retries, self.timeout = max_retries, timeout
        self.last_request = 0.0
        self.requests = 0

    def _wait(self, extra: float = 0.0) -> None:
        pause = self.delay + random.uniform(0, self.jitter) + extra
        remaining = self.last_request + pause - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    def get(self, path: str):
        """Return (status, final_url, content_type, body). Raises on exhausted retries."""
        url = BASE + path
        backoff = 0.0
        for attempt in range(1, self.max_retries + 1):
            self._wait(backoff)
            self.last_request = time.monotonic()
            self.requests += 1
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    ctype = resp.headers.get("Content-Type", "application/octet-stream")
                    return resp.status, resp.geturl(), ctype.lower(), resp.read()
            except urllib.error.HTTPError as e:
                if e.code not in RETRYABLE:
                    return e.code, url, "", b""
                backoff = max(retry_after(e.headers.get("Retry-After")), 2.0 ** attempt * 5)
                log.warning("HTTP %s on %s, backing off %.0fs (attempt %d/%d)",
                            e.code, path, backoff, attempt, self.max_retries)
                err = f"HTTP {e.code}"
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                backoff = 2.0 ** attempt * 5
                log.warning("%s on %s, backing off %.0fs (attempt %d/%d)",
                            e, path, backoff, attempt, self.max_retries)
                err = str(e)
        raise RuntimeError(err)


def retry_after(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return 0.0


def write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, target)


# --------------------------------------------------------------------------- #
# Crawl
# --------------------------------------------------------------------------- #
def crawl(args) -> int:
    site_dir = args.content_dir / "site"
    state = State(args.content_dir / ".state" / "crawl.sqlite")
    state.add(SEEDS)
    requeue = ["failed"] if args.retry_failed else []
    if args.include_assets:
        requeue.append("skipped")
    if args.refresh:
        requeue += ["done", "missing"]
    if (n := state.requeue(requeue)):
        log.info("re-queued %d URLs (%s)", n, ", ".join(requeue))
    fetcher = Fetcher(args.delay, args.jitter, args.max_retries, args.timeout)
    processed = 0
    consecutive_failures = 0

    try:
        while (path := state.next_pending()) is not None:
            if args.max_requests and fetcher.requests >= args.max_requests:
                log.info("reached --max-requests=%d, stopping (resume any time)", args.max_requests)
                break
            if not args.include_assets and is_media(path):
                state.mark(path, "skipped")
                continue

            existing = next((r for r in local_candidates(path) if (site_dir / r).is_file()), None)
            if existing and not args.refresh:
                rel, data = existing, (site_dir / existing).read_bytes()
                base_url = BASE + path
                state.mark(path, "done", local=rel)
            else:
                try:
                    status, final_url, ctype, data = fetcher.get(path)
                except RuntimeError as e:
                    state.mark(path, "failed", error=str(e), attempts=args.max_retries)
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        state.requeue(["failed"])  # not their fault; try them again next run
                        log.error("%d URLs in a row failed (last: %s); the site looks down, "
                                  "stopping. Run again later to resume.", consecutive_failures, e)
                        return EXIT_SITE_DOWN
                    continue
                consecutive_failures = 0
                if status != 200:
                    log.info("%s -> HTTP %s", path, status)
                    state.mark(path, "missing", http_status=status)
                    continue
                final_path = normalize(final_url, BASE + path)
                if urllib.parse.urlsplit(final_url).hostname not in HOSTS:
                    state.mark(path, "offsite", error=f"redirected to {final_url}")
                    continue
                if final_path and final_path != path:
                    state.add([final_path])  # keep the redirect target as its own entry too
                rel = local_for(path, ctype)
                write_atomic(site_dir / rel, data)
                state.mark(path, "done", local=rel, http_status=status, content_type=ctype)
                base_url = final_url

            new = {p for ref in extract_links(data, rel)
                   if (p := normalize(ref, base_url)) is not None}
            state.add(sorted(new))
            processed += 1
            if processed % 50 == 0:
                log.info("progress: %s (requests this run: %d)", state.counts(), fetcher.requests)
            else:
                log.debug("ok %s -> %s", path, rel)
    except KeyboardInterrupt:
        log.info("interrupted; state saved, run again to resume")
        return 130

    log.info("finished run: %s (requests this run: %d)", state.counts(), fetcher.requests)
    return 0


def is_media(path: str) -> bool:
    ext = posixpath.splitext(urllib.parse.unquote(path))[1].lower()
    return ext in ASSET_EXTS - {".css", ".js", ".json", ".ico"}


def status(args) -> int:
    db = args.content_dir / ".state" / "crawl.sqlite"
    if not db.exists():
        print("no crawl state yet")
        return 0
    state = State(db)
    for k, v in sorted(state.counts().items()):
        print(f"{k:>8}: {v}")
    failed = state.db.execute(
        "SELECT path, error FROM urls WHERE status='failed' LIMIT 20").fetchall()
    for p, e in failed:
        print(f"  failed {p}: {e}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content-dir", type=Path, default=DEFAULT_CONTENT_DIR,
                    help="where the mirror and crawl state live (default: %(default)s)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("crawl", help="start or resume the mirror")
    c.add_argument("--delay", type=float, default=1.5, help="seconds between requests (default %(default)s)")
    c.add_argument("--jitter", type=float, default=1.0, help="extra random 0..N seconds (default %(default)s)")
    c.add_argument("--max-retries", type=int, default=5)
    c.add_argument("--timeout", type=float, default=60)
    c.add_argument("--max-requests", type=int, default=0, help="stop after N HTTP requests (0 = no limit)")
    c.add_argument("--no-assets", dest="include_assets", action="store_false",
                   help="skip images/media (pages, css, js, json are still fetched)")
    c.add_argument("--no-retry-failed", dest="retry_failed", action="store_false",
                   help="do not re-queue URLs that failed in earlier runs")
    c.add_argument("--refresh", action="store_true",
                   help="re-download files even if they already exist on disk")
    c.set_defaults(func=crawl)

    s = sub.add_parser("status", help="show crawl progress")
    s.set_defaults(func=status)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
