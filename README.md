# chess-programming-wiki-backup

Keeping this gem, just in case.

This repository is an archival mirror of the [Chess Programming Wiki](https://chessprogramming.org/), together with the tool that makes it.
Since August 2026 the site has been a static, read-only recovery hosted by lichess.org. It offers no MediaWiki dump or API, so the rendered HTML and its images are mirrored instead.
See [docs/research.md](docs/research.md) for the background.

```
.
├── tool/cpw_scraper.py   gentle, resumable scraper (Python 3.9+, stdlib only)
├── tool/crawl_batches.sh crawl in batches, committing and pushing content/ after each
├── content/
│   ├── LICENSE           CC BY-SA 3.0, which covers everything mirrored
│   ├── site/             the mirror, laid out like the site's URL paths
│   └── .state/           crawl.sqlite: crawl queue and status (git-ignored)
├── docs/                 research notes and size estimates
└── LICENSE               MIT, which covers the scripts and docs
```

## Usage

```bash
python3 tool/cpw_scraper.py crawl                     # start, or resume where it stopped
python3 tool/cpw_scraper.py crawl --max-requests 50   # small batch
python3 tool/cpw_scraper.py crawl --no-assets         # pages, CSS and JS only (no images)
python3 tool/cpw_scraper.py status                    # progress summary
BATCH=500 tool/crawl_batches.sh                       # crawl + commit + push to main, batch by batch
```

### Gentle
- Sends one request at a time, waiting 1.5 s plus 0–1 s of random jitter between requests (`--delay`, `--jitter`).
- Honours `Retry-After` and backs off exponentially on 429/5xx and network errors (`--max-retries`).
- Sends an identifying `User-Agent`. Never follows off-site links or URLs with query strings.

### Idempotent and resumable
- Every file is written atomically (`*.part`, then rename), so an interrupted run never leaves a truncated file behind.
- A file that already exists on disk is never downloaded again. Its links are re-read from disk, so the crawl can rebuild itself even without `.state/`, for example on a fresh clone of this repository.
- Stop with Ctrl+C at any time and run the same command again. URLs that failed in earlier runs are retried automatically (`--no-retry-failed` turns that off). `--refresh` re-downloads everything.
- After a `--no-assets` run, running without the flag fetches only the images that were skipped.

### Coverage
It starts from `/`, `/Main_Page`, `/Special:AllPages` (about 4.3k pages) and `/search-index.json`, then follows every on-site link found in the HTML, CSS and JS. That also reaches pages missing from the AllPages list, such as `Category:*` pages, plus images, fonts and stylesheets.
Images that the wiki loads directly from other sites (mostly Wikimedia Commons) are not mirrored.

On disk, file names are %-escaped so they work on any OS, e.g. `/Category:Pioneer` is saved as `content/site/Category%3APioneer.html`.
Links inside the HTML are left untouched, so the mirror is a faithful copy rather than a browsable offline site.

## Licences

- **Scripts and docs:** [MIT](LICENSE).
- **Mirrored content (`content/`):** © the Chess Programming Wiki contributors ([credits](https://chessprogramming.org/Special:Credits)), [CC BY-SA 3.0](content/LICENSE). Any redistribution must keep the attribution and the same licence.
