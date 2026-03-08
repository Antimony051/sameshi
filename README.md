# sameshi

[Watch Demo Video](https://www.youtube.com/watch?v=OkoIb1OAheE)

A minimal chess engine supporting a constrained subset of the game.

`sameshi.h`: 1.95 KB

## attribution

- Engine source repository: https://github.com/datavorous/sameshi

## code variants

The readable version of the code can be found [here](readable/sameshi.h).

## core

1. 120 cell mailbox board
2. negamax search
3. alpha beta pruning
4. material only eval
5. capture first move ordering
6. full legal move validation (check / mate / stalemate)

> [!NOTE]
> not implemented: castling, en passant, promotion, repetition, 50-move rule.

## strength

**~1170 Elo** (95% CI: 1110-1225)  
240 games vs stockfish (1320-1600 levels)  
fixed depth 5, constrained rules, max 60 plies.

## web harness

A local/browser chess app is included to make the engine easy to play and share.

### features

- Visual board UI
- Choose to play as white or black
- Difficulty selection (depth 1 to 6)
- Full chess legality for human moves via `python-chess`
- Commands: undo full move, resign, quit
- Multi-user support: isolated in-memory game per browser session
- Engine subprocess fallback to random legal move if bridge output is invalid
- Health endpoint: `GET /healthz`

## local quick start

1. Build binaries:
   - `make`
2. Create env and install deps:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
3. Run app:
   - `python web_app.py`
4. Open:
   - `http://127.0.0.1:5000`

## cloud VM run (public-facing)

### 1) install deps

- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`
- `make`

### 2) set required env

- `export SAMESHI_SECRET_KEY="<long-random-secret>"`

Optional tuning:

- `export SAMESHI_SESSION_TTL=43200` (12 hours)
- `export SAMESHI_MAX_SESSIONS=2000`
- `export SAMESHI_LOG_LEVEL=INFO`
- `export SAMESHI_COOKIE_SECURE=1` (only when behind HTTPS)

### 3) run with gunicorn

- `pip install gunicorn`
- `gunicorn -w 2 -b 0.0.0.0:8000 web_app:app`

## security notes

- Uses signed session cookies, `HttpOnly`, `SameSite=Strict`.
- Adds strict response headers (CSP, frame deny, nosniff, no-referrer).
- Rejects cross-origin mutating API requests.
- Limits request body size for API safety.
- Game state is in-memory only (not persisted).

## tests

1. Install test deps:
   - `pip install -r requirements-dev.txt`
2. Run tests:
   - `pytest -q`

## bridge binary

`./sameshi_bridge "<fen>" <depth>` prints one UCI move (example: `e2e4`) or `0000`.

The bridge uses the engine in `sameshi.h` without modifying its move-generation limitations.

## TODO

- Add player-selectable promotion piece (currently auto-queen in the web UI).
