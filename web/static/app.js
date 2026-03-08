const PIECE_GLYPHS = {
  P: "♙",
  N: "♘",
  B: "♗",
  R: "♖",
  Q: "♕",
  K: "♔",
  p: "♟",
  n: "♞",
  b: "♝",
  r: "♜",
  q: "♛",
  k: "♚",
};

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];

let state = null;
let selectedSquare = null;
let errorText = "";

function orientation() {
  return state && state.player_color === "black" ? "black" : "white";
}

function buildSquareName(row, col) {
  if (orientation() === "white") {
    return `${FILES[col]}${8 - row}`;
  }
  return `${FILES[7 - col]}${row + 1}`;
}

function isPlayerPiece(symbol) {
  if (!symbol || !state) return false;
  const isWhitePiece = symbol === symbol.toUpperCase();
  return state.player_color === "white" ? isWhitePiece : !isWhitePiece;
}

function legalMovesFrom(square) {
  if (!state) return [];
  return (state.legal_moves || []).filter((move) => move.startsWith(square));
}

function moveDestinations(square) {
  return new Set(legalMovesFrom(square).map((move) => move.slice(2, 4)));
}

function lastMoveSquares() {
  if (!state || !state.last_move || state.last_move.length < 4) {
    return new Set();
  }
  return new Set([state.last_move.slice(0, 2), state.last_move.slice(2, 4)]);
}

async function apiPost(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function renderBoard() {
  const boardEl = document.getElementById("board");
  boardEl.innerHTML = "";

  const destinations = selectedSquare ? moveDestinations(selectedSquare) : new Set();
  const lastSquares = lastMoveSquares();

  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const square = buildSquareName(row, col);
      const piece = (state && state.pieces[square]) || "";
      const glyph = PIECE_GLYPHS[piece] || "";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `square ${(row + col) % 2 === 0 ? "light" : "dark"}`;

      if (square === selectedSquare) btn.classList.add("selected");
      if (destinations.has(square)) btn.classList.add("destination");
      if (lastSquares.has(square)) btn.classList.add("last-move");

      const span = document.createElement("span");
      span.className = "glyph";
      span.textContent = glyph;
      btn.appendChild(span);

      btn.addEventListener("click", () => handleSquareClick(square, piece));
      boardEl.appendChild(btn);
    }
  }
}

function renderStatus() {
  document.getElementById("meta").textContent = state
    ? `You: ${state.player_color} | Engine: ${state.engine_color} | Depth: ${state.depth} | Turn: ${state.turn}`
    : "";
  document.getElementById("status").textContent = state ? state.message : "";
  document.getElementById("error").textContent = errorText;

  if (state) {
    document.getElementById("colorSelect").value = state.player_color;
    document.getElementById("depthSelect").value = String(state.depth);
  }
}

function render() {
  renderBoard();
  renderStatus();
}

async function refreshState() {
  const response = await fetch("/api/state");
  state = await response.json();
  render();
}

async function submitMove(fromSquare, toSquare) {
  try {
    const data = await apiPost("/api/move", { from: fromSquare, to: toSquare });
    state = data.state;
    errorText = "";
  } catch (error) {
    errorText = error.message;
  }
  selectedSquare = null;
  render();
}

async function handleSquareClick(square, piece) {
  if (!state || !state.active) {
    return;
  }
  if (state.turn !== state.player_color) {
    errorText = "Wait for engine move.";
    renderStatus();
    return;
  }

  if (!selectedSquare) {
    if (isPlayerPiece(piece) && legalMovesFrom(square).length > 0) {
      selectedSquare = square;
      errorText = "";
      render();
    }
    return;
  }

  if (square === selectedSquare) {
    selectedSquare = null;
    errorText = "";
    render();
    return;
  }

  if (isPlayerPiece(piece) && legalMovesFrom(square).length > 0) {
    selectedSquare = square;
    errorText = "";
    render();
    return;
  }

  await submitMove(selectedSquare, square);
}

async function startNewGame() {
  const playerColor = document.getElementById("colorSelect").value;
  const depth = Number.parseInt(document.getElementById("depthSelect").value, 10);

  try {
    const data = await apiPost("/api/new", { player_color: playerColor, depth });
    state = data.state;
    selectedSquare = null;
    errorText = "";
  } catch (error) {
    errorText = error.message;
  }
  render();
}

async function undoFullMove() {
  try {
    const data = await apiPost("/api/undo");
    state = data.state;
    selectedSquare = null;
    errorText = "";
  } catch (error) {
    errorText = error.message;
  }
  render();
}

async function resignGame() {
  try {
    const data = await apiPost("/api/resign");
    state = data.state;
    selectedSquare = null;
    errorText = "";
  } catch (error) {
    errorText = error.message;
  }
  render();
}

async function quitGame() {
  try {
    const data = await apiPost("/api/quit");
    state = data.state;
    selectedSquare = null;
    errorText = "";
  } catch (error) {
    errorText = error.message;
  }
  render();
}

function bindControls() {
  document.getElementById("newGameBtn").addEventListener("click", startNewGame);
  document.getElementById("undoBtn").addEventListener("click", undoFullMove);
  document.getElementById("resignBtn").addEventListener("click", resignGame);
  document.getElementById("quitBtn").addEventListener("click", quitGame);
}

window.addEventListener("DOMContentLoaded", async () => {
  bindControls();
  await refreshState();
});
