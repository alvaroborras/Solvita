---
layout: docs
title: GitHub Pages
description: GitHub Pages setup and maintenance notes for Solvita documentation.
active: pages
source_path: docs/pages.md
---

# GitHub Pages

This repository includes a lightweight project-page source under `docs/`.

## Files

| File | Purpose |
| --- | --- |
| `docs/index.md` | Project page landing content. |
| `docs/api.md` | API usage documentation linked from the page and README. |
| `docs/assets/solvita-overview.png` | Paper overview figure rendered for Markdown/GitHub Pages. |

## Enable Pages

In GitHub:

1. Open repository **Settings**.
2. Open **Pages**.
3. Set **Source** to **Deploy from a branch**.
4. Select branch `main` and folder `/docs`.
5. Save.

After GitHub builds the site, the default URL is:

```text
https://nju-link.github.io/Solvita/
```

The README badge already points to that URL.

## Local Preview

Markdown rendering differs slightly from GitHub Pages, but a quick static preview is useful for image paths and links.

```bash
python -m http.server 8000 -d docs
```

Then open:

```text
http://127.0.0.1:8000/
```

## Updating the Overview Figure

The current overview image was rendered from the paper source file `figures/fig2_overview.pdf` for arXiv `2605.15301`.

If the paper source changes, regenerate it from the repository root with:

```bash
pdftoppm -png -singlefile -r 180 /path/to/arxiv-source/figures/fig2_overview.pdf docs/assets/solvita-overview
```
