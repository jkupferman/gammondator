import { api } from "/web/js/api.js";
import { buildAnalysisFeedback, formatTipSummary, renderDiceReadout } from "/web/js/feedback.js";

const HUMAN_SIDE = "black";

const state = {
  sessionId: null,
  position: null,
  legalMoves: [],
  legalMovesLoaded: false,
  moveSteps: [],
  selectedFrom: null,
  submittingMove: false,
  animating: false,
  lastHumanMetricValue: null,
  lastHumanMetricKind: null,
  transientStatus: null,
  transientStatusTimer: null,
  gameOver: false,
  winner: null,
  gameOverHandled: false,
  debugVisible: false,
  clientId: null,
  backend: null,
  fallbackActive: null,
  analyzerDetails: null,
  lastMessage: "Starting up...",
};

const LAST_SESSION_KEY = "gammondator.lastSessionId";
const RECORD_KEY = "gammondator.record";

function disableSoundEffects() {
  if (window.Audio && !window.Audio.__gammondatorMuted) {
    const SilentAudio = function silentAudio() {
      return {
        muted: true,
        volume: 0,
        autoplay: false,
        play: () => Promise.resolve(),
        pause: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
      };
    };
    SilentAudio.__gammondatorMuted = true;
    window.Audio = SilentAudio;
  }

  const mediaProto = window.HTMLMediaElement && window.HTMLMediaElement.prototype;
  if (mediaProto && !mediaProto.__gammondatorMuted) {
    mediaProto.__gammondatorMuted = true;
    mediaProto.play = function playMutedMedia() {
      this.muted = true;
      this.defaultMuted = true;
      this.volume = 0;
      return Promise.resolve();
    };
    mediaProto.load = function loadMutedMedia() {};
  }

  const audioContextNames = ["AudioContext", "webkitAudioContext"];
  for (const name of audioContextNames) {
    const Original = window[name];
    if (!Original || Original.__gammondatorMuted) continue;
    const MutedAudioContext = function mutedAudioContext(...args) {
      const ctx = new Original(...args);
      if (typeof ctx.resume === "function") {
        ctx.resume = () => Promise.resolve();
      }
      if (typeof ctx.suspend === "function") {
        ctx.suspend().catch(() => {});
      }
      return ctx;
    };
    MutedAudioContext.prototype = Original.prototype;
    MutedAudioContext.__gammondatorMuted = true;
    window[name] = MutedAudioContext;
  }
}

disableSoundEffects();

const el = {
  newGameBtn: document.getElementById("newGameBtn"),
  tipBtn: document.getElementById("tipBtn"),
  recordStatus: document.getElementById("recordStatus"),
  turnStatus: document.getElementById("turnStatus"),
  diceStatus: document.getElementById("diceStatus"),
  boardGrid: document.getElementById("boardGrid"),
  offColumn: document.getElementById("offColumn"),
  moveStatus: document.getElementById("moveStatus"),
  feedback: document.getElementById("feedback"),
  debugToggle: document.getElementById("debugToggle"),
  debugPanel: document.getElementById("debugPanel"),
  debugInfo: document.getElementById("debugInfo"),
};

function notify(message, isError = false) {
  state.lastMessage = isError ? `Error: ${message}` : message;
  el.feedback.textContent = isError ? `Error: ${message}` : message;
  renderDebugPanel();
}

function readLastSessionId() {
  const raw = window.localStorage.getItem(LAST_SESSION_KEY);
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function saveLastSessionId(sessionId) {
  if (!sessionId) return;
  window.localStorage.setItem(LAST_SESSION_KEY, String(sessionId));
}

function clearLastSessionId() {
  window.localStorage.removeItem(LAST_SESSION_KEY);
}

function readRecord() {
  const raw = window.localStorage.getItem(RECORD_KEY);
  if (!raw) return { wins: 0, losses: 0 };
  try {
    const parsed = JSON.parse(raw);
    const wins = Number(parsed.wins || 0);
    const losses = Number(parsed.losses || 0);
    return {
      wins: Number.isFinite(wins) ? Math.max(0, Math.floor(wins)) : 0,
      losses: Number.isFinite(losses) ? Math.max(0, Math.floor(losses)) : 0,
    };
  } catch {
    return { wins: 0, losses: 0 };
  }
}

function writeRecord(record) {
  window.localStorage.setItem(RECORD_KEY, JSON.stringify(record));
}

function terminalWinner(position) {
  if (!position) return null;
  if ((position.off_black || 0) >= 15) return "black";
  if ((position.off_white || 0) >= 15) return "white";
  return null;
}

async function handleGameOver(winner) {
  if (!winner || !state.sessionId || state.gameOverHandled) return;
  state.gameOver = true;
  state.winner = winner;
  state.gameOverHandled = true;
  state.moveSteps = [];
  state.selectedFrom = null;
  state.legalMoves = [];
  state.legalMovesLoaded = false;
  render();

  const won = winner === HUMAN_SIDE;
  const record = readRecord();
  if (won) {
    record.wins += 1;
  } else {
    record.losses += 1;
  }
  writeRecord(record);
  notify(won ? "Game complete: You won. Click New Game to play again." : "Game complete: White won. Click New Game to play again.");
  if (readLastSessionId() === state.sessionId) {
    clearLastSessionId();
  }
  try {
    await api(`/sessions/${state.sessionId}/close`, { method: "POST" });
  } catch {
    // If already closed or unavailable, keep UX unblocked.
  }
}


function setTransientStatus(message, isError = false, durationMs = 1800) {
  if (state.transientStatusTimer !== null) {
    clearTimeout(state.transientStatusTimer);
    state.transientStatusTimer = null;
  }
  state.transientStatus = isError ? `Error: ${message}` : message;
  renderStatus();
  state.transientStatusTimer = window.setTimeout(() => {
    state.transientStatus = null;
    state.transientStatusTimer = null;
    renderStatus();
  }, durationMs);
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function clonePosition(position) {
  return {
    points: [...position.points],
    bar_white: position.bar_white,
    bar_black: position.bar_black,
    off_white: position.off_white,
    off_black: position.off_black,
    turn: position.turn,
    cube_value: position.cube_value,
    dice: [position.dice[0], position.dice[1]],
  };
}

function rollOpeningSequence() {
  let blackDie = 1;
  let whiteDie = 1;
  while (blackDie === whiteDie) {
    blackDie = Math.floor(Math.random() * 6) + 1;
    whiteDie = Math.floor(Math.random() * 6) + 1;
  }
  return {
    turn: blackDie > whiteDie ? "black" : "white",
    dice: [blackDie, whiteDie],
  };
}

function startingPosition() {
  const opening = rollOpeningSequence();
  return {
    points: [-2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2],
    bar_white: 0,
    bar_black: 0,
    off_white: 0,
    off_black: 0,
    turn: opening.turn,
    cube_value: 1,
    dice: opening.dice,
  };
}

function renderStatus() {
  const record = readRecord();
  el.recordStatus.textContent = `Record: ${record.wins}-${record.losses}`;

  if (!state.sessionId || !state.position) {
    el.turnStatus.textContent = "Turn: -";
    el.diceStatus.textContent = "Dice: -";
    el.moveStatus.textContent = "Starting up...";
    el.tipBtn.disabled = true;
    return;
  }

  const turnLabel = state.position.turn === HUMAN_SIDE ? "Your turn" : "White turn";
  el.turnStatus.textContent = `Turn: ${turnLabel}`;
  el.diceStatus.innerHTML = renderDiceReadout(state.position.dice[0], state.position.dice[1]);

  let statusText = "Your turn (black). Select checker to move.";
  if (state.gameOver) {
    statusText = state.winner === HUMAN_SIDE ? "Game complete: you won." : "Game complete: white won.";
  } else if (state.submittingMove) {
    statusText = "Submitting move...";
  } else if (state.animating) {
    statusText = "Animating move...";
  } else if (state.position.turn !== HUMAN_SIDE) {
    statusText = "AI is playing white...";
  } else if (!state.legalMovesLoaded) {
    statusText = "Loading legal moves...";
  } else if (state.selectedFrom !== null) {
    statusText = `Selected ${state.selectedFrom}. Pick destination.`;
  } else if (state.moveSteps.length > 0) {
    const notation = state.moveSteps.map((step) => `${step.from_point}/${step.to_point}`).join(" ");
    statusText = `Building move: ${notation}`;
  }
  el.moveStatus.textContent = state.transientStatus || statusText;

  el.tipBtn.disabled =
    !state.position ||
    state.gameOver ||
    state.position.turn !== HUMAN_SIDE ||
    state.submittingMove ||
    state.animating ||
    !state.legalMovesLoaded ||
    state.legalMoves.length === 0;
}

async function animateMoveReplay(startPosition, steps, finalPosition) {
  if (!finalPosition) return;
  const moveSteps = Array.isArray(steps) ? steps : [];
  if (moveSteps.length === 0) {
    state.position = finalPosition;
    render();
    return;
  }

  state.animating = true;
  state.moveSteps = [];
  state.selectedFrom = null;
  let preview = clonePosition(startPosition);
  const side = startPosition.turn;
  state.position = preview;
  render();

  try {
    for (const step of moveSteps) {
      preview = applyPreviewStep(preview, step, side);
      state.position = preview;
      render();
      await sleep(260);
    }
    state.position = finalPosition;
  } finally {
    state.animating = false;
    render();
  }
}

function applyPreviewStep(position, step, side) {
  const next = clonePosition(position);
  const from = Number(step.from_point);
  const to = Number(step.to_point);

  if (side === "white") {
    if (from >= 1 && from <= 24) {
      next.points[from - 1] -= 1;
    } else if (from === 25) {
      next.bar_white -= 1;
    }
  } else {
    if (from >= 1 && from <= 24) {
      next.points[from - 1] += 1;
    } else if (from === 0) {
      next.bar_black -= 1;
    }
  }

  if (to === 0 && side === "white") {
    next.off_white += 1;
  } else if (to === 25 && side === "black") {
    next.off_black += 1;
  } else if (to >= 1 && to <= 24) {
    const idx = to - 1;
    if (side === "white") {
      if (next.points[idx] === -1) {
        next.points[idx] = 0;
        next.bar_black += 1;
      }
      next.points[idx] += 1;
    } else {
      if (next.points[idx] === 1) {
        next.points[idx] = 0;
        next.bar_white += 1;
      }
      next.points[idx] -= 1;
    }
  }

  return next;
}

function projectPositionAfterSteps(position, steps) {
  let preview = clonePosition(position);
  const side = position.turn;
  for (const step of steps) {
    preview = applyPreviewStep(preview, step, side);
  }
  return preview;
}

function workingPosition() {
  if (!state.position) return null;
  if (state.moveSteps.length === 0) return state.position;
  return projectPositionAfterSteps(state.position, state.moveSteps);
}

function getPrefixMatchingMoves() {
  if (state.legalMoves.length === 0) {
    return [];
  }
  const matches = [];
  for (const move of state.legalMoves) {
    if (!Array.isArray(move.steps) || move.steps.length === 0) continue;
    if (state.moveSteps.length >= move.steps.length) continue;

    let prefixMatches = true;
    for (let i = 0; i < state.moveSteps.length; i += 1) {
      const expected = move.steps[i];
      const actual = state.moveSteps[i];
      if (!expected || expected.from_point !== actual.from_point || expected.to_point !== actual.to_point) {
        prefixMatches = false;
        break;
      }
    }
    if (prefixMatches) {
      matches.push(move);
    }
  }
  return matches;
}

function getValidSourcesForPrefix() {
  const sources = new Set();
  for (const move of getPrefixMatchingMoves()) {
    const nextStep = move.steps[state.moveSteps.length];
    if (nextStep) {
      sources.add(nextStep.from_point);
    }
  }
  return sources;
}

function getValidTargetsForSelection() {
  if (state.selectedFrom === null || state.legalMoves.length === 0) {
    return new Set();
  }
  const targets = new Set();
  for (const move of getPrefixMatchingMoves()) {
    const nextStep = move.steps[state.moveSteps.length];
    if (nextStep && nextStep.from_point === state.selectedFrom) {
      targets.add(nextStep.to_point);
    }
  }
  return targets;
}

function exactLegalMoveMatch() {
  if (!state.legalMoves.length || state.moveSteps.length === 0) {
    return null;
  }

  for (const move of state.legalMoves) {
    if (!Array.isArray(move.steps)) continue;
    if (move.steps.length !== state.moveSteps.length) continue;

    let orderedMatch = true;
    for (let i = 0; i < state.moveSteps.length; i += 1) {
      const expected = move.steps[i];
      const actual = state.moveSteps[i];
      if (!expected || expected.from_point !== actual.from_point || expected.to_point !== actual.to_point) {
        orderedMatch = false;
        break;
      }
    }
    if (orderedMatch) {
      return move;
    }
  }

  const playedKey = state.moveSteps
    .map((step) => `${Number(step.from_point)}>${Number(step.to_point)}`)
    .sort()
    .join("|");
  for (const move of state.legalMoves) {
    if (!Array.isArray(move.steps)) continue;
    if (move.steps.length !== state.moveSteps.length) continue;
    const legalKey = move.steps
      .map((step) => `${Number(step.from_point)}>${Number(step.to_point)}`)
      .sort()
      .join("|");
    if (legalKey === playedKey) {
      return move;
    }
  }
  return null;
}

function renderCheckers(side, count) {
  if (count <= 0) return "";
  const visible = Math.min(count, 5);
  const items = [];
  for (let i = 0; i < visible; i += 1) {
    items.push(`<span class="checker ${side}"></span>`);
  }
  if (count > visible) {
    items.push(`<span class="checker-count">+${count - visible}</span>`);
  }
  return items.join("");
}

function renderOffCheckers(side, count) {
  if (!count) return "<span class='off-empty'>0</span>";
  const visible = Math.min(count, 6);
  const items = [];
  for (let i = 0; i < visible; i += 1) {
    items.push(`<span class="checker ${side}"></span>`);
  }
  if (count > visible) {
    items.push(`<span class="checker-count">+${count - visible}</span>`);
  }
  return items.join("");
}

function onPointClick(point) {
  if (!state.position || state.gameOver || state.submittingMove || state.animating || state.position.turn !== HUMAN_SIDE || !state.legalMovesLoaded) {
    return;
  }

  if (state.selectedFrom === point) {
    state.selectedFrom = null;
    render();
    return;
  }

  if (state.selectedFrom === null) {
    chooseSource(point);
  } else {
    chooseDestination(point);
  }
}

function canChooseSource(point) {
  if (!state.position || state.position.turn !== HUMAN_SIDE) return false;
  const position = workingPosition();
  if (!position) return false;
  if (position.bar_black > 0 && point !== 0) return false;

  if (point >= 1 && point <= 24) {
    const value = position.points[point - 1] || 0;
    if (value >= 0) return false;
  } else if (point === 0) {
    if (position.bar_black <= 0) return false;
  } else {
    return false;
  }

  const validSources = getValidSourcesForPrefix();
  if (state.legalMoves.length > 0) {
    return validSources.size > 0 && validSources.has(point);
  }
  return true;
}

async function resyncSessionState() {
  if (!state.sessionId) return;
  const session = await api(`/sessions/${state.sessionId}`);
  if (session.status !== "active") {
    throw new Error(`Session ${state.sessionId} is not active`);
  }
  state.position = session.current_position;
  state.moveSteps = [];
  state.selectedFrom = null;
  state.submittingMove = false;
  state.animating = false;
  state.transientStatus = null;
  render();
  await refreshLegalMoves();
}

function chooseSource(point) {
  if (!canChooseSource(point)) {
    setTransientStatus("That checker is not legal for this step.", true);
    return;
  }
  if (state.selectedFrom === point) {
    state.selectedFrom = null;
  } else {
    state.selectedFrom = point;
  }
  render();
}

function chooseDestination(point) {
  if (!state.position || state.selectedFrom === null) return;

  const validTargets = getValidTargetsForSelection();
  if (state.legalMoves.length > 0 && (validTargets.size === 0 || !validTargets.has(point))) {
    setTransientStatus("That destination is not legal for the selected checker.", true);
    return;
  }

  state.moveSteps.push({ from_point: state.selectedFrom, to_point: point });
  state.selectedFrom = null;

  const exactMatch = exactLegalMoveMatch();
  if (exactMatch) {
    state.moveSteps = exactMatch.steps.map((step) => ({
      from_point: step.from_point,
      to_point: step.to_point,
    }));
  }

  render();
  maybeAutoSubmitBuiltMove();
}

function maybeAutoSubmitBuiltMove() {
  if (!state.position || state.submittingMove || state.animating) return;
  if (state.position.turn !== HUMAN_SIDE) return;
  if (state.selectedFrom !== null || state.moveSteps.length === 0) return;

  const hasContinuation = getPrefixMatchingMoves().length > 0;
  const exactMatch = exactLegalMoveMatch();
  if (!exactMatch && hasContinuation) return;

  if (exactMatch) {
    state.moveSteps = exactMatch.steps.map((step) => ({
      from_point: step.from_point,
      to_point: step.to_point,
    }));
  }

  submitMove();
}

function renderBoard() {
  if (!state.position) {
    el.boardGrid.innerHTML = "";
    el.offColumn.innerHTML = "";
    return;
  }

  const boardPosition = workingPosition();
  if (!boardPosition) {
    return;
  }

  const topLeft = [13, 14, 15, 16, 17, 18];
  const topRight = [19, 20, 21, 22, 23, 24];
  const bottomLeft = [12, 11, 10, 9, 8, 7];
  const bottomRight = [6, 5, 4, 3, 2, 1];
  const validTargets = getValidTargetsForSelection();
  const validSources = getValidSourcesForPrefix();

  function buildPoint(point, orientation, stripeDark) {
    const idx = point - 1;
    const value = boardPosition.points[idx];
    const side = value > 0 ? "white" : value < 0 ? "black" : "empty";
    const count = Math.abs(value);
    const isSelected = state.selectedFrom === point;
    const isValidTarget = validTargets.has(point);
    const canSource =
      state.position.turn === HUMAN_SIDE &&
      state.legalMovesLoaded &&
      !state.submittingMove &&
      (state.selectedFrom === null ? validSources.has(point) : true);

    const pointEl = document.createElement("button");
    pointEl.className = `board-point ${orientation} ${stripeDark ? "dark" : "light"}${isSelected ? " selected" : ""}${isValidTarget ? " valid-target" : ""}`;
    pointEl.disabled = state.submittingMove || state.animating || state.position.turn !== HUMAN_SIDE;
    pointEl.addEventListener("click", () => onPointClick(point));

    const num = document.createElement("span");
    num.className = "point-number";
    num.textContent = String(point);

    const stack = document.createElement("span");
    stack.className = "checker-stack";
    if (side !== "empty" && count > 0) {
      stack.innerHTML = renderCheckers(side, count);
    }

    if (canSource && state.selectedFrom === null) {
      pointEl.title = "Select this checker";
    }

    pointEl.appendChild(num);
    pointEl.appendChild(stack);
    return pointEl;
  }

  function buildHalf(points, orientation) {
    const half = document.createElement("div");
    half.className = "board-half";
    points.forEach((point, idx) => {
      const stripeDark = idx % 2 === 0;
      half.appendChild(buildPoint(point, orientation, stripeDark));
    });
    return half;
  }

  const board = document.createElement("div");
  board.className = "bg-board";

  const topRow = document.createElement("div");
  topRow.className = "board-row top";
  topRow.appendChild(buildHalf(topLeft, "down"));

  const bar = document.createElement("button");
  const barSelected = state.selectedFrom === 0;
  bar.className = `board-bar${barSelected ? " selected" : ""}`;
  bar.disabled = state.submittingMove || state.animating || state.position.turn !== HUMAN_SIDE;
  bar.title = "Select checker from bar";
  bar.innerHTML = `
    <div class="bar-label">BAR</div>
    <div class="bar-counts">W ${boardPosition.bar_white} / B ${boardPosition.bar_black}</div>
    <div class="bar-stack">
      ${renderCheckers("white", boardPosition.bar_white)}
      ${renderCheckers("black", boardPosition.bar_black)}
    </div>
  `;
  bar.addEventListener("click", () => onPointClick(0));
  topRow.appendChild(bar);

  topRow.appendChild(buildHalf(topRight, "down"));

  const bottomRow = document.createElement("div");
  bottomRow.className = "board-row bottom";
  bottomRow.appendChild(buildHalf(bottomLeft, "up"));
  bottomRow.appendChild(document.createElement("div")).className = "board-bar-spacer";
  bottomRow.appendChild(buildHalf(bottomRight, "up"));

  board.appendChild(topRow);
  board.appendChild(bottomRow);
  el.boardGrid.innerHTML = "";
  el.boardGrid.appendChild(board);

  const canBearOffBlack =
    state.position.turn === HUMAN_SIDE &&
    state.selectedFrom !== null &&
    validTargets.has(25) &&
    !state.submittingMove &&
    !state.animating;

  el.offColumn.innerHTML = `
    <button class="off-rail" id="blackOffBtn" ${canBearOffBlack ? "" : "disabled"}>
      <div class="off-title">Black Off (${boardPosition.off_black})</div>
      <div class="off-stack">${renderOffCheckers("black", boardPosition.off_black)}</div>
    </button>
    <button class="off-rail" disabled>
      <div class="off-title">White Off (${boardPosition.off_white})</div>
      <div class="off-stack">${renderOffCheckers("white", boardPosition.off_white)}</div>
    </button>
  `;

  const blackOffBtn = document.getElementById("blackOffBtn");
  if (blackOffBtn) blackOffBtn.addEventListener("click", () => chooseDestination(25));
}

function render() {
  renderStatus();
  renderBoard();
  renderDebugPanel();
}

function renderDebugPanel() {
  if (!el.debugPanel || !el.debugInfo || !el.debugToggle) return;
  el.debugPanel.hidden = !state.debugVisible;
  el.debugToggle.setAttribute("aria-expanded", state.debugVisible ? "true" : "false");

  const lines = [
    `client_id: ${state.clientId || "-"}`,
    `session_id: ${state.sessionId || "-"}`,
    `turn: ${state.position?.turn || "-"}`,
    `dice: ${state.position ? `${state.position.dice[0]}-${state.position.dice[1]}` : "-"}`,
    `backend: ${state.backend || "-"}`,
    `fallback_active: ${state.fallbackActive === null ? "-" : String(state.fallbackActive)}`,
    `analyzer_details: ${state.analyzerDetails || "-"}`,
    `status: ${state.gameOver ? "complete" : state.submittingMove ? "submitting" : state.animating ? "animating" : "ready"}`,
    `last_feedback: ${state.lastMessage || "-"}`,
  ];
  el.debugInfo.textContent = lines.join("\n");
}

function toggleDebugPanel() {
  state.debugVisible = !state.debugVisible;
  renderDebugPanel();
}

async function loadDebugContext() {
  try {
    const [me, analyzer] = await Promise.all([api("/me"), api("/analyzer")]);
    state.clientId = me.client_id || null;
    state.backend = analyzer.backend || null;
    state.fallbackActive = Boolean(analyzer.fallback_active);
    state.analyzerDetails = analyzer.details || null;
  } catch {
    // Debug data is optional and should never block gameplay.
  }
  renderDebugPanel();
}

async function refreshLegalMoves() {
  if (!state.position) {
    state.legalMoves = [];
    state.legalMovesLoaded = false;
    render();
    return;
  }
  const winner = terminalWinner(state.position);
  if (winner) {
    await handleGameOver(winner);
    return;
  }

  state.legalMovesLoaded = false;
  render();

  try {
    const data = await api("/legal-moves", {
      method: "POST",
      body: JSON.stringify({ position: state.position }),
    });
    state.legalMoves = data.moves || [];
    state.legalMovesLoaded = true;
    render();

    if (state.position.turn === HUMAN_SIDE && state.legalMoves.length === 0 && !state.submittingMove) {
      const d1 = state.position.dice[0];
      const d2 = state.position.dice[1];
      const reason = state.position.bar_black > 0
        ? `No legal bar entry on ${d1}-${d2}.`
        : `No legal move on ${d1}-${d2}.`;
      setTransientStatus(`${reason} Auto-passing turn...`, false, 2200);
      await submitPassMove();
    }
  } catch (err) {
    state.legalMoves = [];
    state.legalMovesLoaded = false;
    render();
    notify(err.message, true);
  }
}

async function createNewSession() {
  try {
    const created = await api("/sessions", {
      method: "POST",
      body: JSON.stringify({ initial_position: startingPosition() }),
    });
    state.sessionId = created.session_id;
    saveLastSessionId(state.sessionId);
    state.position = created.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.submittingMove = false;
    state.lastHumanMetricValue = null;
    state.lastHumanMetricKind = null;
    state.gameOver = false;
    state.winner = null;
    state.gameOverHandled = false;
    notify("New game started (new session created).");
    render();
    await refreshLegalMoves();
    await autoAdvanceWhiteTurns();
  } catch (err) {
    notify(err.message, true);
  }
}

async function loadSession(sessionId) {
  try {
    const session = await api(`/sessions/${sessionId}`);
    if (session.status !== "active") {
      clearLastSessionId();
      await createNewSession();
      return;
    }
    state.sessionId = session.session_id;
    saveLastSessionId(state.sessionId);
    state.position = session.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.submittingMove = false;
    state.lastHumanMetricValue = null;
    state.lastHumanMetricKind = null;
    state.gameOver = false;
    state.winner = null;
    state.gameOverHandled = false;
    notify(`Resumed session #${session.session_id}.`);
    render();
    await refreshLegalMoves();
    await autoAdvanceWhiteTurns();
  } catch (err) {
    notify(err.message, true);
  }
}

async function ensureSession() {
  try {
    await loadDebugContext();
    const preferredSessionId = readLastSessionId();
    if (preferredSessionId) {
      try {
        const preferred = await api(`/sessions/${preferredSessionId}`);
        if (preferred.status === "active") {
          await loadSession(preferred.session_id || preferredSessionId);
          return;
        }
        clearLastSessionId();
      } catch {
        clearLastSessionId();
      }
    }
    const sessions = await api("/sessions?status=active");
    const active = Array.isArray(sessions.sessions) ? sessions.sessions : [];
    if (active.length > 0) {
      await loadSession(active[0].session_id);
      return;
    }
    await createNewSession();
  } catch (err) {
    notify(err.message, true);
  }
}

async function autoAdvanceWhiteTurns() {
  if (!state.sessionId || !state.position) return;
  let safety = 0;
  const playedNotations = [];

  while (state.position && state.position.turn === "white" && safety < 12) {
    const startPosition = clonePosition(state.position);
    const ai = await api(`/sessions/${state.sessionId}/ai-turn`, {
      method: "POST",
      body: JSON.stringify({ apply_move: true }),
    });
    if (!ai.current_position) {
      throw new Error("AI turn returned no current position");
    }
    const aiSteps = ai.selected_play?.notation === "pass" ? [] : (ai.selected_play?.steps || []);
    playedNotations.push(ai.selected_play?.notation || ai.selected_move?.notation || "pass");
    await animateMoveReplay(startPosition, aiSteps, ai.current_position);
    state.moveSteps = [];
    state.selectedFrom = null;
    safety += 1;
  }

  if (safety >= 12) {
    throw new Error("AI auto-advance safety limit reached");
  }

  await refreshLegalMoves();
  if (playedNotations.length > 0) {
    notify(`AI played: ${playedNotations.join(" | ")}`);
  }
}

async function submitPassMove() {
  if (!state.sessionId || !state.position || state.gameOver || state.position.turn !== HUMAN_SIDE) return;

  state.submittingMove = true;
  render();
  try {
    const played = await api(`/sessions/${state.sessionId}/play-turn`, {
      method: "POST",
      body: JSON.stringify({
        played_move: {
          notation: "pass",
          steps: [{ from_point: 0, to_point: 0 }],
        },
        record_training: false,
        auto_advance_to_human: true,
      }),
    });
    state.position = played.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    setTransientStatus("Auto-pass applied. White played automatically.", false, 2200);
    await refreshLegalMoves();
  } catch (err) {
    notify(err.message, true);
    try {
      await resyncSessionState();
    } catch (syncErr) {
      notify(syncErr.message, true);
    }
  } finally {
    state.submittingMove = false;
    render();
  }
}

async function submitMove() {
  if (!state.sessionId || !state.position || state.gameOver || state.position.turn !== HUMAN_SIDE) return;
  if (state.submittingMove || state.moveSteps.length === 0) return;

  state.submittingMove = true;
  render();

  try {
    const playedSteps = state.moveSteps.map((step) => ({
      from_point: step.from_point,
      to_point: step.to_point,
    }));
    const notation = playedSteps.map((step) => `${step.from_point}/${step.to_point}`).join(" ");

    const played = await api(`/sessions/${state.sessionId}/play-turn`, {
      method: "POST",
      body: JSON.stringify({
        played_move: { notation, steps: playedSteps },
        record_training: true,
        auto_advance_to_human: true,
      }),
    });

    const humanPosition = played.human_position || played.current_position;
    const startPosition = clonePosition(state.position);
    await animateMoveReplay(startPosition, playedSteps, humanPosition);
    state.moveSteps = [];
    state.selectedFrom = null;
    const aiReplies = Array.isArray(played.auto_ai_turns) ? played.auto_ai_turns : [];
    let aiStart = clonePosition(state.position);
    for (const turn of aiReplies) {
      if (!turn || !turn.current_position) {
        continue;
      }
      const aiSteps = turn.selected_play?.notation === "pass" ? [] : (turn.selected_play?.steps || []);
      await animateMoveReplay(aiStart, aiSteps, turn.current_position);
      aiStart = clonePosition(state.position);
    }
    state.position = played.current_position;
    render();
    const aiSummary = aiReplies.length
      ? `AI replies: ${aiReplies.map((turn) => turn.selected_play?.notation || turn.selected_move?.notation || "pass").join(" | ")}`
      : "";
    const feedback = buildAnalysisFeedback(
      played.analysis,
      state.lastHumanMetricValue,
      state.lastHumanMetricKind,
      aiSummary,
    );
    if (!feedback.ok) {
      notify(feedback.text || "No move analysis available.");
    } else {
      el.feedback.innerHTML = feedback.html;
      state.lastMessage = el.feedback.textContent || "Move analyzed.";
      state.lastHumanMetricValue = feedback.nextHumanMetricValue;
      state.lastHumanMetricKind = feedback.nextHumanMetricKind;
      renderDebugPanel();
    }
    await refreshLegalMoves();
  } catch (err) {
    notify(err.message, true);
    try {
      await resyncSessionState();
    } catch (syncErr) {
      notify(syncErr.message, true);
    }
  } finally {
    state.submittingMove = false;
    render();
  }
}

async function showTip() {
  if (!state.sessionId || !state.position || state.gameOver || state.animating || state.position.turn !== HUMAN_SIDE) return;

  try {
    const suggested = await api(`/sessions/${state.sessionId}/ai-turn`, {
      method: "POST",
      body: JSON.stringify({ apply_move: false }),
    });
    const suggestion = suggested.selected_play;
    notify(formatTipSummary(suggested.selected_move, suggestion));
  } catch (err) {
    notify(err.message, true);
  }
}

el.newGameBtn.addEventListener("click", createNewSession);
el.tipBtn.addEventListener("click", showTip);
if (el.debugToggle) {
  el.debugToggle.addEventListener("click", toggleDebugPanel);
}

ensureSession();
