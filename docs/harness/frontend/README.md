# Frontend — agent protocol (stub)

This repository is a **Python CLI** (`zhvault`). There is no frontend app, package, or UI build.

## Rules for agents

1. Do **not** invent a frontend stack (React/Vue/Vite/Next, CSS frameworks, `package.json`, etc.) unless a human explicitly requests a product UI.
2. Do **not** add frontend lint/build gates to `make gate` without an approved design under `docs/superpowers/specs/`.
3. Obsidian / Hexo / Next consumption of `data/` markdown is **output layout**, not a first-party frontend in this repo.

When a real UI is added, put its agent protocol under this directory and wire Cursor rules accordingly.
