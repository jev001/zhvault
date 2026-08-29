# Original Assets + Obsidian / Static Export Links — Design

**Date:** 2026-08-29  
**Status:** Approved (choice C)  
**Parent:** [2026-08-29-zhihu-backup-design.md](./2026-08-29-zhihu-backup-design.md)

## Goal

1. Download **original** images when Zhihu CDN serves sized variants (`_720w`, etc.); persist **source** and **origin** URLs in meta.
2. Default markdown emit: **HTML comments** (source/origin) + **wikilink** `![[assets/{file}]]`, plus frontmatter `assets: [{path, file, source, origin}]` for Hexo/Next export.
3. Optional `--asset-link rel|wikilink|assets-root` for override; vault / site root = `data/`.

## Non-goals

- Multi-resolution archives (only prefer origin download)
- Auto Hexo/Next project scaffolding
- Rewriting historical MD without `--full`

## URL normalization

Before download, map `source_url` → `origin_url`:

- Strip known size suffixes in the last path segment before extension: `_720w`, `_hd`, `_b`, `_qhd`, `_720x0`, `_1080w`, etc. (regex on filename).
- Only rewrite hosts matching `*.zhimg.com` (and common pic CDNs used by Zhihu); leave other URLs unchanged.
- Try `origin_url` first; on failure fall back to `source_url`.
- Asset cache key / file hash seed: **canonical `origin_url`** when download succeeded via origin or source-after-failed-origin still store under origin key if rewrite applied, else source.

## Meta

Extend asset records (sqlite columns + json object; string path values remain readable as legacy):

- `path`, `source_url`, `origin_url`
- `item_assets` continues to list the **canonical** url used as map key (prefer origin)

## Markdown emit (default = C)

```markdown
<!-- asset-source: https://pic1.zhimg.com/v2-xxx_720w.jpg -->
<!-- asset-origin: https://pic1.zhimg.com/v2-xxx.jpg -->
![[assets/ab12cd34ef567890.jpg]]
```

Frontmatter:

```yaml
assets:
  - file: ab12cd34ef567890.jpg
    path: assets/ab12cd34ef567890.jpg
    source: https://..._720w.jpg
    origin: https://...jpg
```

| `--asset-link` | Body image syntax |
|----------------|-------------------|
| `wikilink` (default) | `![[assets/{file}]]` |
| `rel` | `![](relative/from/md)` (legacy) |
| `assets-root` | `![](/assets/{file})` |

Comments + frontmatter `assets` always written when localization succeeds (all modes).

## Obsidian / Hexo / Next

- Obsidian: open vault at `data/`; default wikilink works.
- Hexo/Next: copy/symlink `data/assets` → site `public/assets` (or `source/assets`); consume frontmatter `assets[].path` or use `--asset-link assets-root`.

## Acceptance

- Fixture CDN URL with `_720w` → download request uses stripped URL (mock); MD has comments + wikilink + frontmatter entry.
- Origin GET fails → falls back to source; still records both URLs.
- `--asset-link rel` restores relative `![](...)`.
- Legacy `assets` string path in json/sqlite still resolves via `get_asset_path`.
