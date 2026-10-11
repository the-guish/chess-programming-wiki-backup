# Research: archiving chessprogramming.org

Notes from October 2026, gathered while deciding how to preserve the wiki.

## Is there an official dump?

No.

- The homepage describes a *"temporary, read-only recovery of the chessprogrammingwiki while a longer-term plan is worked out"* and says editing *"is not possible right now, but will be again soon"*. On August 3, 2026, lichess.org offered to take over hosting, and the footer reads "Hosted with ❤️ by lichess.org".
- The site is no longer a running MediaWiki. Every MediaWiki route tested returns 404 (`api.php`, `Special:Export`, `Special:Statistics`), as do `robots.txt` and `sitemap.xml`. Adding `?action=raw` just returns the rendered HTML, so the original **wikitext cannot be recovered**; only the rendered HTML is available.
- No public XML dump or GitHub mirror was found, including under the `lichess-org` organization.
- The Wayback Machine's availability API returned no snapshot for the current `chessprogramming.org/Main_Page`. The wiki links an older Wayback snapshot of its former Wikispaces home (Feb 2018), but that is a record of the previous host, not a backup of today's wiki.
- Content licence: **CC BY-SA 3.0 Unported**, per [Special:Credits](https://chessprogramming.org/Special:Credits). Mirroring and redistribution are allowed with attribution.

## How the site is served

- The pages are static HTML behind Cloudflare and nginx. All pages report `last-modified: Wed, 05 Aug 2026`, which fits a one-time export.
- Apex host `chessprogramming.org`; `www.` redirects to it with a 308.
- `Special:AllPages` is a single static page linking to about **4,279** pages. `Category:*` pages are not listed there but are linked from article pages.
- Local images live under `/assets/`. Fonts live under `/fonts/`, referenced from `/style.css`. Scripts are `/search.js` (which loads `/search-index.json`) and `/chess-fen.js`. Styles also come from `/vendor/chessground/*.css`.
- Many portraits and artworks are hotlinked from `upload.wikimedia.org` rather than served by the site.

## What the images are

Most pages that have images are about people, engines and historical machines. Technical pages usually open with one decorative artwork, and a few also include a real diagram.

| Page | Local images | Kind |
|---|---|---|
| Cartoons | 24 | computer-chess cartoons |
| Deep Blue | 3 | the machine, its chip, a photo of the team |
| Alan Turing | 2 | a portrait (Wikimedia) and a group photo |
| Alpha-Beta | 2 | an artwork and `Alphabeta.gif`, a search-tree diagram |
| 0x88, Main Page, category pages | 0 | logo only |

## Size estimate

From a sample of 20 random pages and 12 of their images:

| | Sample | Projected (about 4.3k pages) |
|---|---|---|
| HTML | about 16 KB per page on average (largest seen: 150 KB) | about 70–130 MB raw; git compresses it about 3–4× |
| Local images | about 1.35 per page, about 42 KB each (7–145 KB) | about 150–250 MB (less after de-duplication) |
| **Total** | | **roughly 200–300 MB** |

Every file is far below GitHub's 100 MB per-file limit, and the total is well within its recommended repository size (under 1 GB). That is why images are kept in this dedicated repository: it keeps the weight out of unrelated projects.
The sample was small and leaned towards pages starting with digits, A or C, so treat these numbers as a rough range.
