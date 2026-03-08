from __future__ import annotations

import logging
import os
import random
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import chess
from flask import Flask, g, jsonify, render_template, request, session

PROJECT_ROOT = Path(__file__).resolve().parent
BRIDGE_BIN = PROJECT_ROOT / "sameshi_bridge"

SESSION_TTL_SECONDS = int(os.getenv("SAMESHI_SESSION_TTL", "43200"))
MAX_SESSIONS = int(os.getenv("SAMESHI_MAX_SESSIONS", "2000"))
LOG_LEVEL = os.getenv("SAMESHI_LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOG = logging.getLogger("sameshi.web")

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "web" / "templates"),
    static_folder=str(PROJECT_ROOT / "web" / "static"),
)

secret_key = os.getenv("SAMESHI_SECRET_KEY")
if not secret_key:
    secret_key = secrets.token_hex(32)
    LOG.warning(
        "SAMESHI_SECRET_KEY not set. Using an ephemeral key; sessions reset on restart."
    )

app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.getenv("SAMESHI_COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=16 * 1024,
)


@dataclass
class GameState:
    board: chess.Board = field(default_factory=chess.Board)
    player_color: chess.Color = chess.WHITE
    engine_color: chess.Color = chess.BLACK
    depth: int = 4
    active: bool = False
    status: str = "not_started"
    message: str = "Start a new game to begin."
    winner: str | None = None


@dataclass
class SessionState:
    game: GameState = field(default_factory=GameState)
    last_seen: float = field(default_factory=time.time)


SESSIONS: dict[str, SessionState] = {}
STORE_LOCK = threading.Lock()
START_TIME = time.time()


def color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


def parse_color(raw: Any) -> chess.Color:
    return chess.BLACK if str(raw).lower() == "black" else chess.WHITE


def parse_depth(raw: Any) -> int:
    try:
        depth = int(raw)
    except (TypeError, ValueError):
        depth = 4
    return max(1, min(6, depth))


def cleanup_sessions_locked(now: float) -> None:
    expired = [
        sid
        for sid, entry in SESSIONS.items()
        if now - entry.last_seen > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        del SESSIONS[sid]

    overflow = len(SESSIONS) - MAX_SESSIONS
    if overflow > 0:
        oldest = sorted(SESSIONS.items(), key=lambda item: item[1].last_seen)[:overflow]
        for sid, _ in oldest:
            del SESSIONS[sid]


def session_id() -> str:
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(24)
        session["sid"] = sid
    return sid


def current_state_locked() -> tuple[str, GameState]:
    sid = session_id()
    now = time.time()
    cleanup_sessions_locked(now)
    entry = SESSIONS.get(sid)
    if entry is None:
        entry = SessionState()
        SESSIONS[sid] = entry
    entry.last_seen = now
    return sid, entry.game


def state_payload(state: GameState) -> dict[str, Any]:
    board = state.board
    last_move = board.move_stack[-1].uci() if board.move_stack else None
    legal_moves = []
    if state.active and board.turn == state.player_color:
        legal_moves = [m.uci() for m in board.legal_moves]

    pieces = {
        chess.square_name(square): piece.symbol()
        for square, piece in board.piece_map().items()
    }

    return {
        "active": state.active,
        "status": state.status,
        "message": state.message,
        "winner": state.winner,
        "fen": board.fen(),
        "pieces": pieces,
        "turn": color_name(board.turn),
        "player_color": color_name(state.player_color),
        "engine_color": color_name(state.engine_color),
        "depth": state.depth,
        "last_move": last_move,
        "ply_count": len(board.move_stack),
        "legal_moves": legal_moves,
    }


def set_status(state: GameState, note: str | None = None) -> None:
    outcome = state.board.outcome(claim_draw=True)

    if outcome is not None:
        state.active = False
        if outcome.winner is None:
            state.status = "draw"
            state.winner = None
            base = f"Draw ({outcome.termination.name.lower().replace('_', ' ')})."
        else:
            winner = color_name(outcome.winner)
            state.winner = winner
            if outcome.termination == chess.Termination.CHECKMATE:
                state.status = "checkmate"
                base = f"Checkmate. {winner.title()} wins."
            else:
                state.status = "finished"
                base = f"{winner.title()} wins ({outcome.termination.name.lower().replace('_', ' ')})."
        state.message = f"{note} {base}".strip() if note else base
        return

    state.active = True
    state.winner = None
    if state.board.is_check():
        state.status = "check"
        base = f"{color_name(state.board.turn).title()} to move (in check)."
    else:
        state.status = "ongoing"
        base = f"{color_name(state.board.turn).title()} to move."
    state.message = f"{note} {base}".strip() if note else base


def bridge_move(state: GameState, depth: int) -> tuple[chess.Move | None, str | None, bool]:
    legal_moves = list(state.board.legal_moves)
    if not legal_moves:
        return None, None, False

    def random_fallback(reason: str) -> tuple[chess.Move, str, bool]:
        return random.choice(legal_moves), reason, True

    if not BRIDGE_BIN.exists():
        return random_fallback("bridge binary missing")

    try:
        result = subprocess.run(
            [str(BRIDGE_BIN), state.board.fen(), str(depth)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return random_fallback("bridge process error")

    token = result.stdout.strip().split()[0] if result.stdout.strip() else ""
    if not token or token == "0000":
        return random_fallback("bridge returned no move")

    try:
        move = chess.Move.from_uci(token)
    except ValueError:
        return random_fallback("bridge returned invalid uci")

    if move not in state.board.legal_moves:
        return random_fallback(f"bridge returned illegal move {token}")

    return move, None, False


def play_engine_turn_if_needed(state: GameState) -> None:
    if not state.active:
        return
    if state.board.turn != state.engine_color:
        return

    move, fallback_reason, used_fallback = bridge_move(state, state.depth)
    if move is None:
        set_status(state)
        return

    state.board.push(move)
    if used_fallback:
        set_status(state, f"Engine fallback used ({fallback_reason}).")
    else:
        set_status(state, f"Engine played {move.uci()}.")


def parse_json_body() -> tuple[dict[str, Any] | None, Any | None]:
    if not request.is_json:
        return None, (jsonify({"ok": False, "error": "Expected JSON body."}), 415)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"ok": False, "error": "Invalid JSON body."}), 400)

    return payload, None


def is_same_origin() -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True

    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        return False

    return (
        parsed.scheme.lower() == request.scheme.lower()
        and parsed.netloc.lower() == request.host.lower()
    )


@app.before_request
def before_request() -> Any:
    g.request_start = perf_counter()

    if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not is_same_origin():
            return jsonify({"ok": False, "error": "Cross-origin request denied."}), 403
    return None


@app.after_request
def after_request(response):
    elapsed_ms = (perf_counter() - g.request_start) * 1000.0
    sid = session.get("sid", "-")
    LOG.info(
        "request method=%s path=%s status=%s ms=%.1f sid=%s ip=%s",
        request.method,
        request.path,
        response.status_code,
        elapsed_ms,
        sid,
        request.headers.get("X-Forwarded-For", request.remote_addr),
    )

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
    return response


@app.errorhandler(413)
def payload_too_large(_err):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Payload too large."}), 413
    return "Payload too large", 413


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/healthz")
def healthz() -> Any:
    with STORE_LOCK:
        cleanup_sessions_locked(time.time())
        active_sessions = len(SESSIONS)

    return jsonify(
        {
            "status": "ok",
            "uptime_seconds": int(time.time() - START_TIME),
            "active_sessions": active_sessions,
        }
    )


@app.get("/api/state")
def api_state() -> Any:
    with STORE_LOCK:
        _sid, state = current_state_locked()
        return jsonify(state_payload(state))


@app.post("/api/new")
def api_new_game() -> Any:
    payload, err = parse_json_body()
    if err:
        return err

    with STORE_LOCK:
        _sid, state = current_state_locked()
        state.board = chess.Board()
        state.player_color = parse_color(payload.get("player_color", "white"))
        state.engine_color = not state.player_color
        state.depth = parse_depth(payload.get("depth", 4))
        set_status(state, "New game started.")
        play_engine_turn_if_needed(state)
        return jsonify({"ok": True, "state": state_payload(state)})


@app.post("/api/move")
def api_move() -> Any:
    payload, err = parse_json_body()
    if err:
        return err

    src = str(payload.get("from", "")).lower()
    dst = str(payload.get("to", "")).lower()

    with STORE_LOCK:
        _sid, state = current_state_locked()

        if not state.active:
            return jsonify({"ok": False, "error": "No active game.", "state": state_payload(state)}), 400
        if state.board.turn != state.player_color:
            return jsonify({"ok": False, "error": "Not your turn.", "state": state_payload(state)}), 400

        try:
            from_sq = chess.parse_square(src)
            to_sq = chess.parse_square(dst)
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid square.", "state": state_payload(state)}), 400

        piece = state.board.piece_at(from_sq)
        if piece is None or piece.color != state.player_color:
            return jsonify(
                {
                    "ok": False,
                    "error": "Select one of your pieces.",
                    "state": state_payload(state),
                }
            ), 400

        promotion = None
        if piece.piece_type == chess.PAWN and chess.square_rank(to_sq) in (0, 7):
            # TODO: expose promotion choice (q/r/b/n) in the UI.
            promotion = chess.QUEEN

        move = chess.Move(from_sq, to_sq, promotion=promotion)
        if move not in state.board.legal_moves:
            return jsonify({"ok": False, "error": "Illegal move.", "state": state_payload(state)}), 400

        state.board.push(move)
        set_status(state, f"You played {move.uci()}.")
        play_engine_turn_if_needed(state)
        return jsonify({"ok": True, "state": state_payload(state)})


@app.post("/api/undo")
def api_undo() -> Any:
    with STORE_LOCK:
        _sid, state = current_state_locked()

        if len(state.board.move_stack) < 2:
            return jsonify(
                {
                    "ok": False,
                    "error": "At least one full move is required before undo.",
                    "state": state_payload(state),
                }
            ), 400

        state.board.pop()
        state.board.pop()
        set_status(state, "Undid one full move.")
        return jsonify({"ok": True, "state": state_payload(state)})


@app.post("/api/resign")
def api_resign() -> Any:
    with STORE_LOCK:
        _sid, state = current_state_locked()

        if not state.active:
            return jsonify({"ok": False, "error": "No active game.", "state": state_payload(state)}), 400

        winner = color_name(not state.player_color)
        state.active = False
        state.status = "resigned"
        state.winner = winner
        state.message = f"You resigned. {winner.title()} wins."
        return jsonify({"ok": True, "state": state_payload(state)})


@app.post("/api/quit")
def api_quit() -> Any:
    with STORE_LOCK:
        _sid, state = current_state_locked()
        state.board = chess.Board()
        state.active = False
        state.status = "quit"
        state.winner = None
        state.message = "Game ended. Start a new game when ready."
        return jsonify({"ok": True, "state": state_payload(state)})


if __name__ == "__main__":
    host = os.getenv("SAMESHI_HOST", "127.0.0.1")
    port = int(os.getenv("SAMESHI_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
