# learn-streamlit

Interactive git visualizer, sandbox, and level-based tutorial built with Streamlit and a static Pyodide client.

## Play online

GitHub Pages (Pyodide, fully in-browser):

```
https://alisadeghiaghili.github.io/learn-streamlit/
```

## Run locally

### Static site (same as Pages)

```bash
python -m http.server 8000 --directory docs
```

Open `http://127.0.0.1:8000`. The first load downloads Pyodide.

### Streamlit UI

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Tests

```bash
python -m pip install pytest
python -m pytest tests -q
```

## Features

- Live SVG commit graph (older left → newer right)
- Simulated git commands: `commit`, `branch`, `checkout`, `merge`, `rebase`,
  `cherry-pick`, `reset --hard`, `revert`, `tag`, `clone`, `fetch`, `pull`,
  `push`, `fakeTeamwork`, and meta commands `undo` / `reset` / `levels` / `show solution`
- Level catalog with start/goal trees and structural win detection
- Git golf: track commands used vs. the optimal solution

## Project layout

```
app.py                 Streamlit UI (local / Streamlit Cloud)
docs/                  Static GitHub Pages client (Pyodide)
  index.html
  app.js
  styles.css
  bridge.py            Browser session API
  lgb/                 Bundled engine copy (copied in CI)
lgb/                   Pure Python engine (source of truth)
tests/                 Pytest suite
.github/workflows/     CI + Pages deploy
```

## Architecture notes

The engine in `lgb/` is a **structural simulation** of git — no filesystem
index or object database. Goal matching ignores concrete commit ids and
compares ancestor shapes.

GitHub Pages cannot host the Streamlit server, so `docs/` runs the same
engine in the browser via Pyodide. CI copies `lgb/*.py` into `docs/lgb/`
before publishing.
