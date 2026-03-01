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
  lastHumanWinPct: null,
  transientStatus: null,
  transientStatusTimer: null,
};

const el = {
  newGameBtn: document.getElementById("newGameBtn"),
  tipBtn: document.getElementById("tipBtn"),
  sessionStatus: document.getElementById("sessionStatus"),
  turnStatus: document.getElementById("turnStatus"),
  diceStatus: document.getElementById("diceStatus"),
  boardGrid: document.getElementById("boardGrid"),
  offColumn: document.getElementById("offColumn"),
  moveStatus: document.getElementById("moveStatus"),
  feedback: document.getElementById("feedback"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function notify(message, isError = false) {
  el.feedback.textContent = isError ? `Error: ${message}` : message;
}

function diePipPositions(value) {
  const v = Number(value);
  const positions = {
    1: [5],
    2: [1, 9],
    3: [1, 5, 9],
    4: [1, 3, 7, 9],
    5: [1, 3, 5, 7, 9],
    6: [1, 3, 4, 6, 7, 9],
  };
  return positions[v] || [];
}

function renderDieFace(value) {
  const active = new Set(diePipPositions(value));
  const cells = [];
  for (let i = 1; i <= 9; i += 1) {
    cells.push(`<span class="pip-cell">${active.has(i) ? "<span class=\"pip-dot\"></span>" : ""}</span>`);
  }
  return `<span class="die-face" aria-label="Die ${Number(value)}">${cells.join("")}</span>`;
}

function renderDiceReadout(d1, d2) {
  return `<span class="dice-readout"><span class="dice-label">Dice:</span>${renderDieFace(d1)}${renderDieFace(d2)}</span>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function parseNotationSteps(notation) {
  if (!notation) return [];
  return String(notation)
    .trim()
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => token.includes("/"));
}

function humanizeNotation(notation) {
  const steps = parseNotationSteps(notation);
  if (!steps.length) return String(notation || "");
  const humanized = steps.map((step) => {
    const [rawFrom = "", rawTo = ""] = step.split("/");
    const from = rawFrom === "0" || rawFrom === "25" ? "bar" : rawFrom;
    const to = rawTo === "0" || rawTo === "25" ? "off" : rawTo;
    return `${from}/${to}`;
  });
  return humanized.join(" ");
}

function stepEndpointRank(value) {
  const token = String(value || "").toLowerCase();
  if (token === "bar") return -1;
  if (token === "off") return 99;
  const num = Number(token);
  if (Number.isFinite(num)) return num;
  return 50;
}

function canonicalizeNotation(notation) {
  const steps = parseNotationSteps(notation);
  if (!steps.length) return String(notation || "");
  const sorted = [...steps].sort((a, b) => {
    const [af = "", at = ""] = a.split("/");
    const [bf = "", bt = ""] = b.split("/");
    const fromDiff = stepEndpointRank(af) - stepEndpointRank(bf);
    if (fromDiff !== 0) return fromDiff;
    return stepEndpointRank(at) - stepEndpointRank(bt);
  });
  return sorted.join(" ");
}

function countSharedSteps(playedNotation, bestNotation) {
  const played = parseNotationSteps(playedNotation);
  const best = parseNotationSteps(bestNotation);
  if (!played.length || !best.length) {
    return { shared: 0, total: played.length };
  }
  const bestCounts = new Map();
  for (const step of best) {
    bestCounts.set(step, (bestCounts.get(step) || 0) + 1);
  }
  let shared = 0;
  for (const step of played) {
    const remaining = bestCounts.get(step) || 0;
    if (remaining > 0) {
      shared += 1;
      bestCounts.set(step, remaining - 1);
    }
  }
  return { shared, total: played.length };
}

function renderPlayedNotationWithSharedSteps(playedNotation, bestNotation) {
  const played = parseNotationSteps(playedNotation);
  if (!played.length) {
    return escapeHtml(playedNotation || "");
  }
  const best = parseNotationSteps(bestNotation);
  const bestCounts = new Map();
  for (const step of best) {
    bestCounts.set(step, (bestCounts.get(step) || 0) + 1);
  }
  let shared = 0;
  const parts = played.map((step) => {
    const remaining = bestCounts.get(step) || 0;
    if (remaining > 0) {
      shared += 1;
      bestCounts.set(step, remaining - 1);
      return `<span class="feedback-step-shared">${escapeHtml(step)}</span>`;
    }
    return `<span class="feedback-step-normal">${escapeHtml(step)}</span>`;
  });
  if (shared === 0 || shared === played.length) {
    return escapeHtml(playedNotation || "");
  }
  return parts.join(" ");
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

function formatMoveAnalysisSummary(analysis) {
  if (!analysis || !analysis.played_move || !analysis.best_move) {
    return null;
  }
  const played = analysis.played_move;
  const best = analysis.best_move;
  const reasons = Array.isArray(played.why) && played.why.length ? played.why : ["No notes available."];
  const qualityTitle = {
    excellent: "Excellent move.",
    good: "Good move.",
    inaccuracy: "Small miss.",
    mistake: "Mistake.",
    blunder: "Major mistake.",
  }[played.quality] || "Move reviewed.";
  const loss = Number(played.delta_vs_best || 0);
  const isOptimal = loss <= 0.000001;
  const isRoundedZero = Number(loss.toFixed(3)) === 0;
  const isNearOptimal = !isOptimal && isRoundedZero;
  const playedHuman = humanizeNotation(played.notation);
  const bestHuman = humanizeNotation(best.notation);
  const playedDisplay = isOptimal || isNearOptimal ? canonicalizeNotation(playedHuman) : playedHuman;
  const bestDisplay = isOptimal || isNearOptimal ? canonicalizeNotation(bestHuman) : bestHuman;
  const headline = isOptimal ? "Optimal move." : isNearOptimal ? "Near-optimal move." : qualityTitle;
  const currentWinPct = estimateWinPctFromEquity(played.equity);
  const winDelta = state.lastHumanWinPct === null ? null : currentWinPct - state.lastHumanWinPct;
  const sharedSteps = countSharedSteps(playedDisplay, bestDisplay);
  const lossHint =
    isOptimal
      ? "You found an optimal move."
      : isNearOptimal
      ? "Essentially tied with best line at displayed precision."
      : loss < 0.02
      ? "You were very close to optimal."
      : loss < 0.08
        ? "There was a slightly stronger option."
        : loss < 0.2
          ? "There was a clearly better option."
          : "This choice gives up a lot of equity.";
  const firstReason = reasons[0] || "No notes available.";
  const whyPrefix = isOptimal || isNearOptimal ? "Trade-off note" : "Why";
  const nextStep = buildNextStepAdvice({
    isOptimal,
    playedNotation: playedDisplay,
    bestNotation: bestDisplay,
    firstReason,
    equityLoss: loss,
  });
  const winPctLine =
    winDelta === null
      ? `Win %: ${currentWinPct.toFixed(1)}%`
      : `Win %: ${currentWinPct.toFixed(1)}% (${winDelta >= 0 ? "+" : ""}${winDelta.toFixed(1)}%)`;
  const nextStepLine = isOptimal ? null : `Takeaway: ${nextStep}`;
  state.lastHumanWinPct = currentWinPct;
  return {
    quality: played.quality,
    qualityTitle: headline,
    playedNotation: playedDisplay,
    bestLine: bestDisplay,
    equityLossLine: `Equity loss: ${loss.toFixed(3)}. ${lossHint}`,
    winPctValue: currentWinPct,
    winDelta,
    whyLine: `${whyPrefix}: ${firstReason}`,
    nextStepLine,
    sharedSteps,
  };
}

function buildNextStepAdvice({ isOptimal, playedNotation, bestNotation, firstReason, equityLoss }) {
  if (isOptimal) {
    return "You matched the engine's top plan in this position.";
  }
  const reason = (firstReason || "").toLowerCase();
  if (reason.includes("race")) {
    return "Engine preference: maximize pip efficiency while keeping risk controlled.";
  }
  if (reason.includes("blot")) {
    return "Engine preference: safer checker distribution and lower tactical exposure.";
  }
  if (reason.includes("anchor")) {
    return "Engine preference: preserve or improve anchor quality.";
  }
  if (reason.includes("hit")) {
    return "Engine preference: stronger contact sequence than the played line.";
  }
  if (reason.includes("bar")) {
    return "Engine preference: cleaner bar-entry structure with fewer follow-up liabilities.";
  }
  if (reason.includes("bear")) {
    return "Engine preference: more efficient bear-off pattern.";
  }
  if (equityLoss < 0.05) {
    return "Close decision: the engine found a slightly more efficient line.";
  }
  if (playedNotation !== bestNotation) {
    return "Engine preference: a different line with better overall equity.";
  }
  return "Engine preference: a line with better balance between safety and efficiency.";
}

function estimateWinPctFromEquity(equity) {
  const normalized = Math.max(-1, Math.min(1, Number(equity) || 0));
  return 50 + normalized * 50;
}

function renderAnalysisFeedback(analysis, aiSummary = "") {
  const summary = formatMoveAnalysisSummary(analysis);
  if (!summary) {
    notify("No move analysis available.");
    return;
  }
  const qualityClass = `quality-${summary.quality || "good"}`;
  const hasDelta = summary.winDelta !== null;
  const normalizedDelta = hasDelta ? Number(summary.winDelta.toFixed(1)) : null;
  const isFlatDelta = normalizedDelta !== null && Math.abs(normalizedDelta) < 0.1;
  const deltaText =
    !hasDelta
      ? ""
      : isFlatDelta
        ? "(no change)"
        : `(${normalizedDelta >= 0 ? "+" : ""}${normalizedDelta.toFixed(1)}%)`;
  const deltaClass =
    !hasDelta || isFlatDelta ? "delta-flat" : normalizedDelta >= 0 ? "delta-up" : "delta-down";
  const playedWithShared = renderPlayedNotationWithSharedSteps(summary.playedNotation, summary.bestLine);
  const sharedInfo = countSharedSteps(summary.playedNotation, summary.bestLine);
  const bestLineClass =
    sharedInfo.total > 0 && sharedInfo.shared > 0 ? "feedback-best-line" : "feedback-step-normal";
  const lines = [
    `<span class="feedback-quality ${qualityClass}">${escapeHtml(summary.qualityTitle)}</span>`,
    `You played: ${playedWithShared}`,
    `Best line: <span class="${bestLineClass}">${escapeHtml(summary.bestLine)}</span>`,
  ];
  lines.push(escapeHtml(summary.equityLossLine));
  lines.push(
    `Win Pct: ${summary.winPctValue.toFixed(1)}%` +
      (deltaText ? ` <span class="feedback-win-delta ${deltaClass}">${escapeHtml(deltaText)}</span>` : ""),
  );
  lines.push(escapeHtml(summary.whyLine));
  if (summary.nextStepLine) {
    lines.push(escapeHtml(summary.nextStepLine));
  }
  if (aiSummary) {
    lines.push("");
    lines.push(escapeHtml(aiSummary));
  }
  el.feedback.innerHTML = lines.join("\n");
}

function formatTipSummary(selectedMove, suggestion) {
  if (!selectedMove || !suggestion) {
    return "No tip available right now.";
  }
  const reasons = Array.isArray(selectedMove.why) && selectedMove.why.length ? selectedMove.why : [];
  const leadReason = reasons[0] ? `\nReason: ${reasons[0]}` : "";
  return `Tip: consider ${suggestion.notation}\nThis is rated ${selectedMove.quality} (equity ${selectedMove.equity.toFixed(3)}).${leadReason}`;
}

function renderStatus() {
  if (!state.sessionId || !state.position) {
    el.sessionStatus.textContent = "Session: -";
    el.turnStatus.textContent = "Turn: -";
    el.diceStatus.textContent = "Dice: -";
    el.moveStatus.textContent = "Starting up...";
    el.tipBtn.disabled = true;
    return;
  }

  el.sessionStatus.textContent = `Session: #${state.sessionId}`;
  el.turnStatus.textContent = `Turn: ${state.position.turn}`;
  el.diceStatus.innerHTML = renderDiceReadout(state.position.dice[0], state.position.dice[1]);

  let statusText = "Your turn (black). Select checker to move.";
  if (state.submittingMove) {
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
  const visible = Math.min(count, 8);
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
  if (!state.position || state.submittingMove || state.animating || state.position.turn !== HUMAN_SIDE || !state.legalMovesLoaded) {
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
}

async function refreshLegalMoves() {
  if (!state.position) {
    state.legalMoves = [];
    state.legalMovesLoaded = false;
    render();
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
      body: JSON.stringify({ initial_position: startingPosition(), profile_id: "default" }),
    });
    state.sessionId = created.session_id;
    state.position = created.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.submittingMove = false;
    state.lastHumanWinPct = null;
    notify("New game started.");
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
      await createNewSession();
      return;
    }
    state.sessionId = session.session_id;
    state.position = session.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.submittingMove = false;
    state.lastHumanWinPct = null;
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
    const sessions = await api("/sessions?profile_id=default&status=active");
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
  if (!state.sessionId || !state.position || state.position.turn !== HUMAN_SIDE) return;

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
  if (!state.sessionId || !state.position || state.position.turn !== HUMAN_SIDE) return;
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
    renderAnalysisFeedback(played.analysis, aiSummary);
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
  if (!state.sessionId || !state.position || state.animating || state.position.turn !== HUMAN_SIDE) return;

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

ensureSession();
