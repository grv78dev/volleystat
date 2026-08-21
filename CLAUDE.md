# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Deploy after every code change

This repo is pushed to a private GitHub repository (`grv78dev/volleystat`, remote `origin`, branch `main`). After making any code change (not docs-only chatter), in addition to whatever else the task requires: `git add` the relevant files, commit with a message describing the change, and `git push`. Do this without asking for confirmation each time — it's pre-authorized. `data/` stays gitignored (real player data, including minors) and must never be committed.

## What this project is

VolleyStat is an offline-first, single-user web app for tracking volleyball match statistics in real time. It is written in Italian and designed for Italian-speaking volleyball teams. The entire backend is a single Flask file (`app.py`, ~2550 lines) with Jinja2 templates and file-based JSON storage. There is no database, no test suite, and no build step.

## Running the app

```bash
bash install.sh   # first time: creates .venv and installs Flask
bash run.sh       # start the server at http://127.0.0.1:8000
```

Or directly:
```bash
python3 app.py
```

The server binds to `0.0.0.0:8000` so it is reachable from tablets on the LAN.

## Architecture

The backend is split into three Python files:

| File | Purpose | Lines |
|---|---|---|
| `parser.py` | `COMMANDS` dict + `parse_command` + `compute_state`. No Flask, no I/O. | ~176 |
| `stats.py` | Domain constants (zones, rotations) + all pure `compute_*` functions that take `sd` dicts. No Flask, no I/O. | ~930 |
| `app.py` | I/O helpers + `compute_match_*` orchestrators (call storage + stats) + `category_season_stats` + `compute_player_trends` + `_build_stats` + `build_ai_export` + 22 Flask routes. | ~1840 |

`app.py` imports from both modules:
```python
from parser import parse_command, compute_state
from stats import (compute_player_stats, enrich_stats, pct, ...)
```

### Data storage

Pure JSON on disk, no migrations needed:

```
data/
├── club.json
├── categories.json
└── categorie/
    └── <cat_id>/
        ├── info.json
        ├── players.json
        ├── matches.json
        └── sets/
            └── <match_id>_<set_n>.json
```

Set data (`<match_id>_<set_n>.json`) is an append-only list of events. All derived state is recomputed by replaying them — there is no stored mutable state inside a set.

### Request cycle for a live match

1. User types a command (e.g. `A10`, `R+15`, `SUB10/12`) in `set.html`.
2. Browser POSTs to `/c/<cat_id>/partita/<match_id>/set/<set_num>/comando`.
3. `parse_command(raw)` decodes the string into a structured event dict.
4. The event is appended to the set's JSON file via `_jsave()`.
5. `compute_state(sd)` replays all events to derive current score, rotation, and lineup.
6. The browser polls `/stato` (GET) every 2 seconds to refresh the live view.

### Key domain functions

| Function | Role |
|---|---|
| `parse_command(raw)` | Parses the command language → event dict |
| `compute_state(sd)` | Replays events → score, serve, lineup, rotation |
| `compute_player_stats(sd)` | Per-player raw stat counts from a single set |
| `enrich_stats(raw_stats)` | Adds `rec_efficiency`, `att_efficiency`, totals to raw counts |
| `_build_stats(cat_id, match_id)` | Aggregates all sets of a match; used by `stats_view` and `report_view` |
| `compute_game_continuity(sd)` | Links R+ events to subsequent attacks; cambio-palla analysis |
| `compute_setter_stats(sd)` | Heatmap and zone displacement for the setter |
| `compute_attack_zone_stats(sd, players_by_num)` | Attack distribution by zone with role-aware correction |
| `compute_rotation_stats(sd)` | Point balance broken down by rotation |
| `compute_score_timeline(sd)` | Point-by-point SVG timeline data |
| `compute_minutes_played(sd)` | Actual minutes per player from timestamps and substitution events |
| `compute_player_trends(cat_id)` | Multi-match trend metrics per player (trend, consistency, ravvicinate, pts/set) |
| `category_season_stats(cat_id)` | Season-wide aggregation across all completed matches |
| `build_ai_export(cat_id, match_id)` | Serialises a match to text for pasting into an AI assistant |
| `_jload()` / `_jsave()` | JSON file I/O helpers |

### Route map

| Route | Function | Description |
|---|---|---|
| `/` | `home` | Club hub — manage categories |
| `/c/<cat_id>/` | `index` | Category dashboard |
| `/c/<cat_id>/rosa` | `roster` | Player roster + trend stats |
| `/c/<cat_id>/calendario` | `calendar` | Match calendar |
| `/c/<cat_id>/partita/<id>` | `match_view` | Match overview |
| `/c/<cat_id>/partita/<id>/set/<n>` | `set_view` | Live tracking UI |
| `/c/<cat_id>/partita/<id>/set/<n>/comando` | `add_command` | POST: accept command string |
| `/c/<cat_id>/partita/<id>/set/<n>/stato` | `set_state_api` | GET: polled JSON state |
| `/c/<cat_id>/partita/<id>/statistiche` | `stats_view` | Full match stats |
| `/c/<cat_id>/partita/<id>/report` | `report_view` | Printable match report |
| `/c/<cat_id>/partita/<id>/report-sintetico` | `report_sintetico` | Lega Volley–style PDF |
| `/c/<cat_id>/partita/<id>/esporta-ai` | `esporta_ai` | AI export text |
| `/c/<cat_id>/giocatore/<num>/report` | `report_giocatore` | Per-player printable report |
| `/c/<cat_id>/report-stagione` | `report_stagione` | Season report |
| `/confronto` | `confronto` | Cross-category comparison |
| `/esporta-backup` / `/importa-backup` | — | Full JSON backup zip |

### Templates

All in `templates/`. Heavy ones with significant inline JS:
- `set.html` — live tracking, keyboard command input
- `stats.html` — full match statistics with heatmaps and charts
- `report.html` — printable match report

Static assets: `static/style.css` (dark/light theme via CSS variables), `static/report_base.css` (print styles), `static/app.js` (auto-focus shortcut only).

## Command language

The live input uses volleyball-specific shorthand. All commands are case-insensitive.

| Pattern | Meaning |
|---|---|
| `S<n>` / `SE<n>` | Ace / service error by player `n` |
| `A<n>` / `AE<n>` / `AB<n>` / `ABN<n>` | Attack kill / error / blocked (point) / blocked (in play) |
| `AN<n>` | Attack in campo (no point) |
| `B<n>` / `BE<n>` | Block point / error |
| `R+<n>` / `R-<n>` / `RE<n>` | Good / poor / aced reception |
| `D<n>` / `DE<n>` | Dig / dig error |
| `P` / `PE` | Generic point (opponent error) / point to opponent |
| `SUB<a>/<b>` | Substitution: player `a` out, player `b` in |
| `LIB<a>/<b>` | Libero swap |
| `AUTOLIB` | Toggle automatic middle/libero rotation for the set |
| `W<zone>` | Setter's current zone (1–6, FIPAV standard) |
| `T` / `TO` | Our timeout / opponent timeout |
| `UNDO` | Roll back the last event |

## Domain notes

- **Event sourcing:** `compute_state` is a pure replay over the event list. Never mutate past events — always append or undo.
- **Rotation:** when serve changes, `compute_state` rotates the lineup array left by one (`cur = cur[1:] + cur[:1]`). Position 0 is always the server. The array is kept "by zone": `lineup[i-1]` is the player in FIPAV zone `i` (this invariant is preserved by the left rotation), so slot (index+1) == zone and `SLOT_TO_ZONE` is the identity. Rotations are named by setter zone (`P1`..`P6`, temporal order `ROT_ORDER = [1,6,5,4,3,2]`).
- **Ruleset:** each set has a `ruleset` field (`'standard'` or `'pgs'`). PGS sets go to 17 with no tie-break.
- **Categoria** is the top-level grouping (team/age group). A club has multiple categories.
- **All UI labels, comments, and JSON data keys are in Italian.**
- `compute_player_trends` uses `(pts_scored − pts_lost) / sets_played` as its base efficiency index. "Partite ravvicinate" means matches within 7 days of an adjacent match.
- `compute_minutes_played` relies on `timestamp` fields in events (HH:MM:SS). If no timestamps exist it returns 1 minute per player as a fallback.
- **Auto libero (`auto_libero` flag on the set):** when enabled and a `libero` is set, `_find_auto_libero_event` in `app.py` appends real `libero_exchange` events with `auto: True` after each point/substitution (and at set start): the libero enters for a role-`C` player in the back row (zones 5, 6, or 1 only when receiving — the libero never serves) and the replaced middle re-enters when rotation would put the libero front row or at serve. `UNDO` removes auto events together with the event that generated them.
