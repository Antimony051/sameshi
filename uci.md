```
# Minimal UCI Engine (MVP) — Implementation Spec

This document defines the **minimum required behavior and commands** for a chess engine that can communicate with a UCI-compatible GUI (Universal Chess Interface). It is intentionally scoped to **only what’s needed to be usable** by most GUIs.

If you implement exactly what’s in this file, you will have a working “minimal viable” UCI engine.

---

## 1) Transport and General Rules

### 1.1 Process model
- The engine is a normal executable.
- It **starts**, then **waits for commands on STDIN**.
- It **writes responses to STDOUT**.

### 1.2 Message format
- All communication is **plain text**.
- Every command sent by the GUI ends with a newline (`\n`).
- Every response the engine sends **must also end with `\n`**.
- Treat line endings robustly (`\n`, `\r\n`, etc.). Read lines in text mode.

### 1.3 Whitespace and unknown tokens
- Arbitrary whitespace between tokens is allowed.
- If the engine receives:
  - an **unknown command**, or
  - an **unknown token** inside a known command,
  
  it must **ignore the unknown parts** and try to parse the rest of the line.

### 1.4 Forced mode (important)
- The engine must **never start searching** until it receives a `go` command.
- Before any search, the GUI will send a `position` command.

### 1.5 Concurrency requirement (critical)
- The engine must be able to **read and process input even while searching**.
- At minimum, while searching it must still handle:
  - `stop`
  - `isready`
  - `quit`
- This usually implies:
  - a search thread + an input thread, or
  - a single-threaded loop that checks for input frequently.

### 1.6 Output buffering
- After writing a line to STDOUT, **flush** output so the GUI receives it immediately.

---

## 2) Move Encoding (UCI Move Format)

Moves are in **long algebraic / coordinate notation**:

- Normal moves: `e2e4`, `g1f3`
- Castling: encoded as king move, e.g. `e1g1` (white short), `e1c1` (white long)
- Promotions: add the promoted piece letter in lowercase:
  - `e7e8q`, `a2a1n`, etc.
- “Null move” (engine → GUI only, rarely used): `0000`

You must be able to **parse** these moves when they appear in `position ... moves ...`.

---

## 3) Minimal State Machine

You don’t need many states, but you must behave consistently.

### 3.1 Suggested states
- **BOOT**: engine started, waiting for commands
- **UCI_MODE**: after `uci` handshake is completed
- **IDLE/READY**: not searching, accepts new commands
- **SEARCHING**: after `go`, until search ends or `stop` arrives
- **EXITING**: after `quit`

### 3.2 High-level rules
- `uci` puts engine into UCI mode (handshake).
- `position` sets the internal board position (in IDLE/READY).
- `go` starts searching from the current internal position.
- Every `go` must eventually be followed by exactly one `bestmove ...` output.
- `stop` ends searching ASAP and triggers `bestmove ...`.
- `isready` must be answered with `readyok` **even during search**, without stopping the search.
- `quit` exits ASAP (stop search if needed, then exit).

---

## 4) Required Commands (GUI → Engine)

These are the **minimum required inputs** your engine must understand.

---

### 4.1 `uci`
**Purpose:** Switch engine to UCI mode and perform identification handshake.

**GUI sends:**
```
uci
```
**Engine must respond:**
1) `id name <engine name>`
2) `id author <author>`
3) `uciok`

Example:
```
id name MyEngine 0.1
id author Your Team
uciok
```
**Notes:**
- The engine may also send `option ...` lines, but for MVP they are optional.
- The GUI expects `uciok`. If not received, the GUI may kill the engine.

---

### 4.2 `isready`
**Purpose:** Synchronization / “ping”.

**GUI sends:**
```
isready
```
**Engine must respond:**
```
readyok
```
**Critical requirement:**
- Must respond **immediately**, even while searching.
- Must not stop or reset search just because `isready` arrives.

---

### 4.3 `ucinewgame`
**Purpose:** Indicates the next searches are for a new game.

**GUI sends:**
```
ucinewgame
```
**Engine behavior (MVP):**
- Clear any game-specific state you maintain (e.g., caches tied to game history).
- For MVP it is acceptable to treat as a no-op, but you must not crash or misbehave.

**Important:**
- GUIs often send `isready` after `ucinewgame`. Ensure you answer `readyok`.

---

### 4.4 `position ...`
**Purpose:** Set up the internal board position before searching.

**Forms:**
1) Start position:
```
position startpos
```
2) Start position plus moves:
```
position startpos moves e2e4 e7e5 g1f3
```
3) FEN position:
```
position fen <fenstring>
```
4) FEN position plus moves:
```
position fen <fenstring> moves <m1> <m2> ...
```
**Minimum required behavior:**
- Support **both** `startpos` and `fen`.
- Support the optional `moves` list.
- Apply moves in order to reach the final position.

**Parsing notes:**
- The token `moves` (if present) indicates the remainder of the line is a list of UCI moves.
- FEN is a space-containing string. Parsing approach:
  - After `position fen`, consume tokens until you have the full FEN (typically 6 fields),
  - then if the next token is `moves`, treat the rest as moves.
- If moves are illegal/unparseable:
  - For MVP: ignore the bad move(s) and keep going, or stop applying moves after the first error.
  - Do not crash.

---

### 4.5 `go ...`
**Purpose:** Start searching from the currently set position.

**GUI sends:**
```
go [optional parameters...]
```
**MVP required behavior:**
- Start searching and eventually output:
```
bestmove <move>
```
- You may ignore most `go` parameters, but you must:
- accept them syntactically (don’t crash),
- and follow the “unknown token” rule (ignore what you don’t support).

**Highly recommended minimal subset to support (easy + common):**
- `depth <x>`: search to a fixed depth (plies)
- `movetime <x>`: search exactly `<x>` milliseconds
- `infinite`: search until `stop`

**Common time controls (optional but useful):**
- `wtime <ms>`, `btime <ms>`, `winc <ms>`, `binc <ms>`, `movestogo <n>`

For MVP, if you don’t implement time management:
- If `movetime` is provided, use it.
- Else if `depth` is provided, use it.
- Else if `infinite` is present, run until `stop`.
- Else choose a safe default (e.g., fixed small time like 100ms) so the engine responds.

**Important:**
- Do not start pondering automatically.
- Do not output `bestmove` until you have stopped searching or decided your result.

---

### 4.6 `stop`
**Purpose:** Stop the current search.

**GUI sends:**
```
stop
````
**Engine behavior:**
- If currently searching:
  - stop ASAP
  - then output:
    ```
    bestmove <move>
    ```
- If not searching:
  - ignore.

**Guarantee:**
- Every `go` must produce exactly one `bestmove ...` eventually. `stop` is the usual trigger.

---

### 4.7 `quit`
**Purpose:** Terminate the engine.

**GUI sends:**
````
quit
```
**Engine behavior:**
- Exit ASAP.
- If currently searching, stop it promptly and exit.
- Do not hang.

---

## 5) Required Outputs (Engine → GUI)

These are the **minimum required outputs** your engine must produce.

---

### 5.1 `id name ...` and `id author ...`
Must be sent after `uci`:
```
id name <text>
id author <text>
```
---

### 5.2 `uciok`
Sent after the engine has finished sending `id` (and any `option` lines, if any):
```
uciok
```
---

### 5.3 `readyok`
Sent in response to every `isready`:
```
readyok
```
This must be sent even during search, and promptly.

---

### 5.4 `bestmove <move> [ponder <move>]`
At minimum you must send:
```
bestmove <move>
```
- `<move>` must be a legal UCI move string like `e2e4`.
- You may optionally add `ponder <move2>`, but MVP can omit it.

**Critical rule:**  
For every `go` command, the engine must eventually output exactly one `bestmove ...`.

---

## 6) Minimal “Happy Path” Conversation Example

Typical GUI ↔ engine exchange:

**GUI → Engine**
```
uci
```
**Engine → GUI**
```
id name MyEngine 0.1
id author Your Team
uciok
```
**GUI → Engine**
```
isready
```
**Engine → GUI**
```
readyok
```
**GUI → Engine**
```
ucinewgame
isready
```
**Engine → GUI**
```
readyok
```
**GUI → Engine**
```
position startpos moves e2e4 e7e5
go movetime 1000
```
**Engine → GUI**
```
bestmove g1f3
```
**GUI → Engine**
```
quit
```
---

## 7) Implementation Checklist (MVP)

### Must-have (compatibility critical)
- [ ] Read lines from STDIN until EOF or `quit`
- [ ] `uci` → print `id name`, `id author`, then `uciok`
- [ ] `isready` → always print `readyok` (even while searching)
- [ ] `ucinewgame` → accept (no-op ok)
- [ ] `position startpos ...` → set up internal board + apply moves
- [ ] `position fen ...` → parse FEN + apply moves
- [ ] `go ...` → start search, later output exactly one `bestmove ...`
- [ ] `stop` → end search ASAP and output `bestmove ...`
- [ ] `quit` → exit ASAP
- [ ] Ignore unknown commands/tokens without crashing
- [ ] Process input while searching (at least stop/isready/quit)

### Nice-to-have (but not required for MVP)
- `info ...` output during search (depth/nodes/score/pv)
- Minimal time management for `wtime/btime/winc/binc/movestogo`
- `setoption` support (Hash, Threads, etc.)

---

## 8) Minimal Testing Scripts

### 8.1 Smoke test (handshake + move)
Send this to the engine:
```
uci
isready
ucinewgame
isready
position startpos moves e2e4 e7e5
go movetime 200
stop
quit
```
Expected:
- Must include `uciok`
- Must include `readyok` twice
- Must include exactly one `bestmove ...` for the `go` (it may appear before `stop` if your search ends early)

### 8.2 “isready during search” test
Send:
```
uci
isready
position startpos
go infinite
isready
isready
stop
quit
```
Expected:
- The engine must respond `readyok` to both `isready` lines while still searching.
- After `stop`, must output `bestmove ...`.

---

## 9) Notes on Simplifying the Chess Part (Allowed for MVP)

A “minimal” engine can be extremely simple:
- If you can generate legal moves and pick one (even random), that’s acceptable.
- The UCI compatibility requirements are mostly about **protocol correctness**.

However, you must ensure:
- `bestmove` is always a syntactically valid UCI move (or `0000` as a last resort).
- You don’t deadlock when handling `stop`, `isready`, or `quit`.

---

## 10) Summary of Minimum Required Commands

### GUI → Engine (must implement)
- `uci`
- `isready`
- `ucinewgame`
- `position`
- `go`
- `stop`
- `quit`

### Engine → GUI (must output)
- `id name ...`
- `id author ...`
- `uciok`
- `readyok`
- `bestmove ...`

---

End of spec.
```
