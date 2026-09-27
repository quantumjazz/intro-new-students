# Intro Game: „Две трети от средното“

The classroom game from the first-year intro lecture (`../vavedenie.qmd`).
Students scan the QR code on the first two slides, enter a name and a number
from 0 to 100, and the one closest to 2/3 of the class average wins. The
instructor closes the game from the admin page; the results slide of the deck
(or the standalone results page) reveals the outcome step by step.

Mirrors the sibling course apps (`session-quiz`, `labor-auction-sim`,
`matching-dashboard` in `Courses/society_economics_business`): Python 3
stdlib HTTP server + SQLite, vanilla JS frontend, no build step, no
third-party dependencies. Like `session-quiz`, the backend serves the
frontend itself, so the whole app lives at one address:
**https://intro.visiometrica.com**.

## Pages

| Page | URL | For | What it does |
|------|-----|-----|--------------|
| `index.html` | `/` | Students (phones) | Name + number; can be changed while the game is open. After the reveal: own place, distance, "how many moves ahead". |
| `admin.html` | `/admin` | Instructor | Create and open a game, close it, reveal results to the phones, hide joke entries, CSV export. |
| `results.html` | `/results` | Projector | 1920×1080 poster in the deck's style. Steps: count → distribution → mean → 2/3 → winner → how many moves ahead. Keys: → ← PageDown PageUp Space, F fullscreen, R refresh. `?game=CODE` for an older game. |

`results.html?embed=1` is what the deck loads into its results slide: no key
hints, and the steps come from the deck's fragments via `postMessage`
(see `../live-results.html`). If the page cannot be reached, the slide keeps
its own hand-raising ladder, so the same six clicks still work offline.

## Game flow

1. Before the lecture: `/admin` → admin key → **Създай и отвори**. The newest
   game is always the current one; creating a new game closes any open one.
2. Students answer (one entry per phone; resubmitting replaces it).
3. While the game is open the public API exposes only the count, never the
   running average, so nobody can aim at it.
4. **Затвори играта** (the deck notes put this on the "neighbour" slide).
   The results slide and `/results` now show everything.
5. Optional: **Покажи на телефоните**. Each phone shows its place, the
   target and the level it reached.

"How many moves ahead" uses level-k rungs at 50·(2/3)^k: 50, 33, 22, 15, 10
and 0, with each band ending halfway between rungs (over 42 = 0 moves, 28–42
= 1 move, 19–28 = 2, 12–19 = 3, 1–12 = 4+, 0–1 = all the way).

## Run locally

```bash
cd backend
INTRO_ADMIN_KEY=dev python3 server.py
```

It listens on port 8004. Open `http://localhost:8004/`, `/admin` (key `dev`)
and `/results`. To test the deck against it, open
`../vavedenie.html?results=http://localhost:8004`.

Smoke test (uses the running server's database, so not the class one):

```bash
python3 smoke_test.py --admin dev
```

To reset a local database: `rm backend/data/intro.db*`.

## Configuration

| Var | Default | Purpose |
|---|---|---|
| `INTRO_ADMIN_KEY` | _empty_ | Required for `/api/admin/*` when set. Empty = no key (see below). |
| `INTRO_ALLOWED_ORIGIN` | _empty (any)_ | CORS origin, only needed if the pages are hosted elsewhere. |
| `INTRO_DB_PATH` | `backend/data/intro.db` | SQLite path. |
| `INTRO_FRONTEND_DIR` | `../frontend` | Static files to serve. |

Port **8004**, on the 800x series of the class apps on the laptop (labor 8002,
quiz 8003; 8790 is CourseBench).

**Admin key: none, by decision (2026-09-27).** The laptop runs the game
without `INTRO_ADMIN_KEY`, so `/admin` opens without a key, and so does
everything it can do: anyone who finds `intro.visiometrica.com/admin` can
create, close, reveal or delete a game. To add a key later, put
`INTRO_ADMIN_KEY=…` in `intro-game/.env` on the laptop (mode 600, not in git)
and restart the service; the admin page then asks for it.

## API

Public:

- `GET /api/health`
- `GET /api/game/current` → `{game}` (code, title, status, count) or `{game: null}`
- `POST /api/game/current/entry` `{client_token, name, value}` → `{game, entry}`
- `GET /api/game/current/me?client_token=…` → `{game, entry, result}`; `result` only after the reveal
- `GET /api/game/current/results`, `GET /api/game/{code}/results` → while open `{ready: false, count}`; after closing also `values`, `mean`, `target`, `winners`, `levels`, `target_level`

Admin (`X-Admin-Key` or `X-Admin-Key-B64`):

- `GET /api/admin/games`, `POST /api/admin/games` `{title?}`
- `GET /api/admin/games/{code}` → game, all entries with distances, results
- `POST /api/admin/games/{code}/status` `{status: open | closed | revealed}`
- `POST /api/admin/games/{code}/entries/{id}` `{hidden: bool}`
- `GET /api/admin/games/{code}/csv`, `DELETE /api/admin/games/{code}`

`client_token` is a random id the phone keeps in `localStorage`; it is how
"one entry per phone" works. Names are stored as typed and appear only for
the winner (projector) and in the admin page and CSV.

## Deployment on the Ubuntu laptop

Same pattern as the other apps on the ThinkPad: a clone under
`/home/victor/apps/`, one systemd unit, and the Cloudflare Tunnel
`laptop-server` sending the hostname straight to a port on `127.0.0.1`.

| | |
|---|---|
| Clone | `/home/victor/apps/intro-new-students` |
| Service | `intro-game` (`deploy/intro-game.service`), `/usr/bin/python3`, no venv |
| Port | `8004` on `127.0.0.1` |
| Data | `intro-game/backend/data/intro.db` in the clone (not in git) |
| Address | `https://intro.visiometrica.com` |

First install:

```bash
cd /home/victor/apps
git clone git@github.com:quantumjazz/intro-new-students.git
cloudflared tunnel route dns laptop-server intro.visiometrica.com
sudo bash intro-new-students/intro-game/deploy/install.sh
```

`install.sh` copies the unit, enables and starts it, adds the hostname to the
tunnel config that the `cloudflared` unit actually reads (after a backup, and
only if `cloudflared ... ingress validate` accepts the result), restarts
`cloudflared`, and checks `/api/health`. Running it again changes nothing.

Updating after a push:

```bash
cd /home/victor/apps/intro-new-students && git pull
sudo systemctl restart intro-game
```

A change to the frontend alone needs no restart. Logs:
`sudo journalctl -u intro-game -n 50 --no-pager`.

## Limits (on purpose)

- One entry per phone, not per person: a determined student can clear the
  browser and answer twice. Hide duplicates or joke names from `/admin`.
- No per-IP limits: the whole hall usually shares one campus IP.
- The 2/3 factor is fixed; it is in the rules on the slides.
- The game title is the instructor's own label: only the admin API returns it.
