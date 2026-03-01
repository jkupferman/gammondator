const state = {
  sessionId: null,
  position: null,
  legalMoves: [],
  moveSteps: [],
  selectedFrom: null,
  dragFrom: null,
  touchDragging: false,
  animating: false,
  animationSeq: 0,
  activeStepHighlight: null,
  lastReplay: null,
  lastMoveHighlight: null,
  highlightTimerId: null,
  moveLog: [],
  currentDrill: null,
};

const el = {
  die1: document.getElementById("die1"),
  die2: document.getElementById("die2"),
  animationMs: document.getElementById("animationMs"),
  profileId: document.getElementById("profileId"),
  newSessionBtn: document.getElementById("newSessionBtn"),
  loadLegalBtn: document.getElementById("loadLegalBtn"),
  aiTurnBtn: document.getElementById("aiTurnBtn"),
  rollBtn: document.getElementById("rollBtn"),
  autoAiToggle: document.getElementById("autoAiToggle"),
  sessionReportBtn: document.getElementById("sessionReportBtn"),
  closeSessionBtn: document.getElementById("closeSessionBtn"),
  refreshSessionsBtn: document.getElementById("refreshSessionsBtn"),
  sessionPicker: document.getElementById("sessionPicker"),
  resumeSessionBtn: document.getElementById("resumeSessionBtn"),
  loadDrillBtn: document.getElementById("loadDrillBtn"),
  sessionStatus: document.getElementById("sessionStatus"),
  boardGrid: document.getElementById("boardGrid"),
  offTrays: document.getElementById("offTrays"),
  turnLabel: document.getElementById("turnLabel"),
  animationStatus: document.getElementById("animationStatus"),
  barOffLabel: document.getElementById("barOffLabel"),
  cubeLabel: document.getElementById("cubeLabel"),
  fromBarBtn: document.getElementById("fromBarBtn"),
  toOffBtn: document.getElementById("toOffBtn"),
  undoStepBtn: document.getElementById("undoStepBtn"),
  clearMoveBtn: document.getElementById("clearMoveBtn"),
  replayMoveBtn: document.getElementById("replayMoveBtn"),
  currentMove: document.getElementById("currentMove"),
  submitMoveBtn: document.getElementById("submitMoveBtn"),
  legalMoves: document.getElementById("legalMoves"),
  feedback: document.getElementById("feedback"),
  moveLog: document.getElementById("moveLog"),
  trainingSummary: document.getElementById("trainingSummary"),
  cubeAction: document.getElementById("cubeAction"),
  cubeCheckBtn: document.getElementById("cubeCheckBtn"),
  cubeFeedback: document.getElementById("cubeFeedback"),
  analysisMode: document.getElementById("analysisMode"),
  queueAnalysisBtn: document.getElementById("queueAnalysisBtn"),
  runNextAnalysisBtn: document.getElementById("runNextAnalysisBtn"),
  retryLatestJobBtn: document.getElementById("retryLatestJobBtn"),
  cleanupJobsBtn: document.getElementById("cleanupJobsBtn"),
  analysisJobs: document.getElementById("analysisJobs"),
  drillStatus: document.getElementById("drillStatus"),
  drillAnswer: document.getElementById("drillAnswer"),
  submitDrillBtn: document.getElementById("submitDrillBtn"),
};

function notify(text, isError = false) {
  el.feedback.textContent = isError ? `Error: ${text}` : text;
}

function renderAnimationStatus() {
  el.animationStatus.textContent = state.animating ? "Animating..." : "Idle";
}

function savePreferences() {
  window.localStorage.setItem("gammondator.profileId", el.profileId.value || "default");
  window.localStorage.setItem("gammondator.autoAi", el.autoAiToggle.checked ? "1" : "0");
  window.localStorage.setItem("gammondator.animationMs", String(el.animationMs.value || "320"));
}

function loadPreferences() {
  const profileId = window.localStorage.getItem("gammondator.profileId");
  if (profileId) {
    el.profileId.value = profileId;
  }
  const autoAi = window.localStorage.getItem("gammondator.autoAi");
  el.autoAiToggle.checked = autoAi === "1";
  const animationMs = window.localStorage.getItem("gammondator.animationMs");
  if (animationMs) {
    el.animationMs.value = animationMs;
  }
}

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

function currentDice() {
  return [Number(el.die1.value), Number(el.die2.value)];
}

function currentProfileId() {
  const value = (el.profileId.value || "").trim();
  return value || "default";
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function animationStepMs() {
  const parsed = Number(el.animationMs.value);
  if (!Number.isFinite(parsed)) return 320;
  return Math.max(120, Math.min(900, parsed));
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

function clearStepHighlight() {
  state.activeStepHighlight = null;
}

function resetAnimationState() {
  state.animationSeq += 1;
  state.animating = false;
  clearStepHighlight();
  renderAnimationStatus();
}

function setLastReplay(startPosition, steps, finalPosition) {
  state.lastReplay = {
    startPosition: clonePosition(startPosition),
    steps: steps.map((step) => ({ from_point: step.from_point, to_point: step.to_point })),
    finalPosition: clonePosition(finalPosition),
  };
}

function applyAnimatedStep(position, step, side) {
  const next = clonePosition(position);
  const from = Number(step.from_point);
  const to = Number(step.to_point);
  const hit = { point: null, side: null };

  if (side === "white") {
    if (from >= 1 && from <= 24) {
      next.points[from - 1] -= 1;
    } else if (from === 25) {
      next.bar_white -= 1;
    }
  } else if (side === "black") {
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
        hit.point = to;
        hit.side = "black";
      }
      next.points[idx] += 1;
    } else {
      if (next.points[idx] === 1) {
        next.points[idx] = 0;
        next.bar_white += 1;
        hit.point = to;
        hit.side = "white";
      }
      next.points[idx] -= 1;
    }
  }

  return { position: next, hit };
}

function summarizeStepEvents(startPosition, steps) {
  let preview = clonePosition(startPosition);
  const side = startPosition.turn;
  let hits = 0;
  for (const step of steps) {
    const applied = applyAnimatedStep(preview, step, side);
    preview = applied.position;
    if (applied.hit.point !== null) {
      hits += 1;
    }
  }
  return { hits };
}

async function animateMoveReplay(startPosition, steps, finalPosition) {
  if (!Array.isArray(steps) || steps.length === 0) {
    state.position = finalPosition;
    renderBoard();
    return;
  }

  const seq = state.animationSeq + 1;
  state.animationSeq = seq;
  state.animating = true;
  clearStepHighlight();
  clearMoveHighlight(false);
  renderAnimationStatus();
  refreshButtons();
  renderMoveBuilder();

  let preview = clonePosition(startPosition);
  const side = startPosition.turn;
  state.position = preview;
  renderBoard();

  for (const step of steps) {
    if (state.animationSeq !== seq) {
      return;
    }
    const applied = applyAnimatedStep(preview, step, side);
    preview = applied.position;
    state.position = preview;
    state.activeStepHighlight = {
      from: Number(step.from_point),
      to: Number(step.to_point),
      hitPoint: applied.hit.point,
      hitSide: applied.hit.side,
    };
    renderBoard();
    await sleep(animationStepMs());
  }

  if (state.animationSeq !== seq) {
    return;
  }
  clearStepHighlight();
  state.position = finalPosition;
  state.animating = false;
  renderAnimationStatus();
  refreshButtons();
  renderBoard();
}

function clearMoveHighlight(shouldRender = true) {
  if (state.highlightTimerId !== null) {
    clearTimeout(state.highlightTimerId);
    state.highlightTimerId = null;
  }
  state.lastMoveHighlight = null;
  if (shouldRender) {
    renderBoard();
  }
}

function setMoveHighlightFromSteps(steps) {
  if (!Array.isArray(steps) || steps.length === 0) {
    clearMoveHighlight();
    return;
  }

  const sourcePoints = new Set();
  const targetPoints = new Set();
  let barActive = false;
  let offWhiteActive = false;
  let offBlackActive = false;

  for (const step of steps) {
    if (!step) continue;
    const from = Number(step.from_point);
    const to = Number(step.to_point);

    if (from >= 1 && from <= 24) {
      sourcePoints.add(from);
    } else if (from === 0 || from === 25) {
      barActive = true;
    }

    if (to >= 1 && to <= 24) {
      targetPoints.add(to);
    } else if (to === 0) {
      offWhiteActive = true;
    } else if (to === 25) {
      offBlackActive = true;
    }
  }

  if (state.highlightTimerId !== null) {
    clearTimeout(state.highlightTimerId);
    state.highlightTimerId = null;
  }
  state.lastMoveHighlight = {
    sourcePoints,
    targetPoints,
    barActive,
    offWhiteActive,
    offBlackActive,
  };
  renderBoard();
  state.highlightTimerId = window.setTimeout(() => {
    state.lastMoveHighlight = null;
    state.highlightTimerId = null;
    renderBoard();
  }, 900);
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
    if (!prefixMatches) continue;
    matches.push(move);
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

function canChooseSource(point) {
  if (!state.position || state.animating) {
    return false;
  }
  const turn = state.position.turn;
  if (point >= 1 && point <= 24) {
    const value = state.position.points[point - 1] || 0;
    if (turn === "white" && value <= 0) return false;
    if (turn === "black" && value >= 0) return false;
  } else if (point === 25) {
    if (turn !== "white" || state.position.bar_white <= 0) return false;
  } else if (point === 0) {
    if (turn !== "black" || state.position.bar_black <= 0) return false;
  } else {
    return false;
  }

  const validSources = getValidSourcesForPrefix();
  if (validSources.size > 0) {
    return validSources.has(point);
  }
  return true;
}

function clearDragState() {
  state.dragFrom = null;
  state.touchDragging = false;
}

function chooseSource(point, showErrors = true) {
  if (!state.position) return false;
  if (!canChooseSource(point)) {
    if (showErrors) {
      notify("That checker is not legal for this step.", true);
    }
    return false;
  }
  state.selectedFrom = point;
  renderMoveBuilder();
  renderBoard();
  return true;
}

function chooseDestination(point, showErrors = true) {
  if (!state.position || state.selectedFrom === null || state.animating) return false;
  const validTargets = getValidTargetsForSelection();
  if (validTargets.size > 0 && !validTargets.has(point)) {
    if (showErrors) {
      notify("That destination is not legal for the selected checker.", true);
    }
    return false;
  }
  state.moveSteps.push({ from_point: state.selectedFrom, to_point: point });
  state.selectedFrom = null;
  clearDragState();
  renderMoveBuilder();
  renderBoard();
  return true;
}

function onCheckerDragStart(event) {
  const fromPoint = Number(event.currentTarget.dataset.fromPoint);
  if (!chooseSource(fromPoint, false)) {
    event.preventDefault();
    notify("That checker is not legal for this step.", true);
    return;
  }
  state.dragFrom = fromPoint;
  event.currentTarget.classList.add("dragging");
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(fromPoint));
  }
}

function onCheckerDragEnd(event) {
  event.currentTarget.classList.remove("dragging");
  clearDragState();
  renderBoard();
}

function onCheckerTouchStart(event) {
  const fromPoint = Number(event.currentTarget.dataset.fromPoint);
  if (!chooseSource(fromPoint, false)) {
    notify("That checker is not legal for this step.", true);
    return;
  }
  state.dragFrom = fromPoint;
  state.touchDragging = true;
}

function canDropOn(targetPoint) {
  if (state.selectedFrom === null && state.dragFrom !== null) {
    state.selectedFrom = state.dragFrom;
  }
  if (state.selectedFrom === null) return false;
  const validTargets = getValidTargetsForSelection();
  if (validTargets.size === 0) return true;
  return validTargets.has(targetPoint);
}

function onPointDragOver(event) {
  const targetPoint = Number(event.currentTarget.dataset.point);
  if (!Number.isNaN(targetPoint) && canDropOn(targetPoint)) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
  }
}

function onPointDrop(event) {
  event.preventDefault();
  const targetPoint = Number(event.currentTarget.dataset.point);
  if (Number.isNaN(targetPoint)) return;
  if (state.selectedFrom === null && state.dragFrom !== null) {
    state.selectedFrom = state.dragFrom;
  }
  chooseDestination(targetPoint, true);
}

function onPointTouchEnd(event) {
  if (!state.touchDragging) return;
  event.preventDefault();
  const targetPoint = Number(event.currentTarget.dataset.point);
  if (Number.isNaN(targetPoint)) return;
  if (state.selectedFrom === null && state.dragFrom !== null) {
    state.selectedFrom = state.dragFrom;
  }
  chooseDestination(targetPoint, true);
}

function onOffDrop(event) {
  event.preventDefault();
  if (!state.position) return;
  const offPoint = state.position.turn === "white" ? 0 : 25;
  if (state.selectedFrom === null && state.dragFrom !== null) {
    state.selectedFrom = state.dragFrom;
  }
  chooseDestination(offPoint, true);
}

function onOffDragOver(event) {
  if (!state.position) return;
  const offPoint = state.position.turn === "white" ? 0 : 25;
  if (canDropOn(offPoint)) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
  }
}

async function refreshLegalMoves(silent = true) {
  if (!state.position) {
    state.legalMoves = [];
    renderLegalMoves();
    renderBoard();
    return;
  }

  try {
    const data = await api("/legal-moves", {
      method: "POST",
      body: JSON.stringify({ position: state.position }),
    });
    state.legalMoves = data.moves;
    renderLegalMoves();
    renderBoard();
    if (!silent) {
      notify(`Loaded ${data.moves.length} legal moves.`);
    }
  } catch (err) {
    if (!silent) {
      notify(err.message, true);
    }
  }
}

function renderBoard() {
  if (!state.position) {
    el.boardGrid.innerHTML = "";
    el.offTrays.innerHTML = "";
    renderAnimationStatus();
    return;
  }
  renderAnimationStatus();

  el.turnLabel.textContent = `Turn: ${state.position.turn}`;
  el.barOffLabel.textContent = `Bar W/B: ${state.position.bar_white}/${state.position.bar_black} | Off W/B: ${state.position.off_white}/${state.position.off_black}`;
  el.cubeLabel.textContent = `Cube: ${state.position.cube_value} | Dice: ${state.position.dice[0]}-${state.position.dice[1]}`;

  const topLeft = [13, 14, 15, 16, 17, 18];
  const topRight = [19, 20, 21, 22, 23, 24];
  const bottomLeft = [12, 11, 10, 9, 8, 7];
  const bottomRight = [6, 5, 4, 3, 2, 1];
  const validTargets = getValidTargetsForSelection();

  function buildPoint(point, orientation, stripeDark) {
    const idx = point - 1;
    const value = state.position.points[idx];
    const side = value > 0 ? "white" : value < 0 ? "black" : "empty";
    const count = Math.abs(value);
    const pointEl = document.createElement("button");
    const isSelected = state.selectedFrom === point;
    const isValidTarget = validTargets.has(point);
    const isMoveSource = Boolean(state.lastMoveHighlight?.sourcePoints?.has(point));
    const isMoveTarget = Boolean(state.lastMoveHighlight?.targetPoints?.has(point));
    const isStepSource = state.activeStepHighlight?.from === point;
    const isStepTarget = state.activeStepHighlight?.to === point;
    const isHitPoint = state.activeStepHighlight?.hitPoint === point;
    pointEl.className = `board-point ${orientation} ${stripeDark ? "dark" : "light"}${isSelected ? " selected" : ""}${isValidTarget ? " valid-target" : ""}${isMoveSource || isStepSource ? " move-source" : ""}${isMoveTarget || isStepTarget ? " move-target" : ""}${isHitPoint ? " move-hit" : ""}`;
    pointEl.dataset.point = String(point);
    pointEl.addEventListener("click", () => onPointClick(point));
    pointEl.addEventListener("dragover", onPointDragOver);
    pointEl.addEventListener("drop", onPointDrop);
    pointEl.addEventListener("touchend", onPointTouchEnd, { passive: false });

    const num = document.createElement("span");
    num.className = "point-number";
    num.textContent = String(point);
    pointEl.appendChild(num);

    const stack = document.createElement("div");
    stack.className = "checker-stack";
    if (side !== "empty") {
      const visible = Math.min(count, 5);
      const canDragFromPoint = canChooseSource(point);
      for (let i = 0; i < visible; i += 1) {
        const checker = document.createElement("span");
        checker.className = `checker ${side}`;
        checker.dataset.fromPoint = String(point);
        checker.draggable = canDragFromPoint;
        if (canDragFromPoint) {
          checker.classList.add("draggable");
          checker.addEventListener("dragstart", onCheckerDragStart);
          checker.addEventListener("dragend", onCheckerDragEnd);
          checker.addEventListener("touchstart", onCheckerTouchStart, { passive: true });
        }
        stack.appendChild(checker);
      }
      if (count > 5) {
        const extra = document.createElement("span");
        extra.className = "checker-count";
        extra.textContent = `+${count - 5}`;
        stack.appendChild(extra);
      }
    }
    pointEl.appendChild(stack);
    return pointEl;
  }

  function buildHalf(points, orientation) {
    const half = document.createElement("div");
    half.className = "board-half";
    points.forEach((point, i) => {
      half.appendChild(buildPoint(point, orientation, i % 2 === 0));
    });
    return half;
  }

  const board = document.createElement("div");
  board.className = "bg-board";

  const topRow = document.createElement("div");
  topRow.className = "board-row top";
  topRow.appendChild(buildHalf(topLeft, "down"));

  const bar = document.createElement("div");
  const barSourceActive =
    Boolean(state.lastMoveHighlight?.barActive) ||
    state.activeStepHighlight?.from === 0 ||
    state.activeStepHighlight?.from === 25;
  const barHitActive = Boolean(state.activeStepHighlight?.hitSide);
  bar.className = `board-bar${state.selectedFrom === 25 || state.selectedFrom === 0 ? " selected" : ""}${barSourceActive ? " move-source" : ""}${barHitActive ? " move-hit" : ""}`;
  const barLabel = document.createElement("div");
  barLabel.className = "bar-label";
  barLabel.textContent = "BAR";
  bar.appendChild(barLabel);

  const barCounts = document.createElement("div");
  barCounts.className = "bar-counts";
  barCounts.textContent = `W ${state.position.bar_white} / B ${state.position.bar_black}`;
  bar.appendChild(barCounts);

  const barStack = document.createElement("div");
  barStack.className = "bar-stack";

  const whiteVisible = Math.min(state.position.bar_white, 2);
  for (let i = 0; i < whiteVisible; i += 1) {
    const checker = document.createElement("span");
    checker.className = "checker white";
    if (canChooseSource(25)) {
      checker.classList.add("draggable");
      checker.dataset.fromPoint = "25";
      checker.draggable = true;
      checker.addEventListener("dragstart", onCheckerDragStart);
      checker.addEventListener("dragend", onCheckerDragEnd);
      checker.addEventListener("touchstart", onCheckerTouchStart, { passive: true });
    }
    barStack.appendChild(checker);
  }
  if (state.position.bar_white > 2) {
    const extra = document.createElement("span");
    extra.className = "checker-count";
    extra.textContent = `+${state.position.bar_white - 2}`;
    barStack.appendChild(extra);
  }

  const blackVisible = Math.min(state.position.bar_black, 2);
  for (let i = 0; i < blackVisible; i += 1) {
    const checker = document.createElement("span");
    checker.className = "checker black";
    if (canChooseSource(0)) {
      checker.classList.add("draggable");
      checker.dataset.fromPoint = "0";
      checker.draggable = true;
      checker.addEventListener("dragstart", onCheckerDragStart);
      checker.addEventListener("dragend", onCheckerDragEnd);
      checker.addEventListener("touchstart", onCheckerTouchStart, { passive: true });
    }
    barStack.appendChild(checker);
  }
  if (state.position.bar_black > 2) {
    const extra = document.createElement("span");
    extra.className = "checker-count";
    extra.textContent = `+${state.position.bar_black - 2}`;
    barStack.appendChild(extra);
  }
  bar.appendChild(barStack);
  bar.title = "Click to select checker from bar";
  bar.addEventListener("click", () => chooseFromBar());
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

  const off = document.createElement("div");
  off.className = "off-trays-inner";
  off.innerHTML = `
    <div class="off-tray${state.lastMoveHighlight?.offWhiteActive || state.activeStepHighlight?.to === 0 ? " move-target" : ""}">
      <div class="off-title">White Off</div>
      <div class="off-stack">${renderOffCheckers("white", state.position.off_white)}</div>
    </div>
    <div class="off-tray${state.lastMoveHighlight?.offBlackActive || state.activeStepHighlight?.to === 25 ? " move-target" : ""}">
      <div class="off-title">Black Off</div>
      <div class="off-stack">${renderOffCheckers("black", state.position.off_black)}</div>
    </div>
  `;
  el.offTrays.innerHTML = "";
  el.offTrays.appendChild(off);
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

function renderMoveBuilder() {
  const validTargets = getValidTargetsForSelection();
  const offPoint = state.position ? (state.position.turn === "white" ? 0 : 25) : null;

  if (state.moveSteps.length === 0) {
    el.currentMove.textContent = "No move selected";
  } else {
    const text = state.moveSteps.map((s) => `${s.from_point}/${s.to_point}`).join(" ");
    el.currentMove.textContent = text;
  }
  el.clearMoveBtn.disabled = state.moveSteps.length === 0;
  el.undoStepBtn.disabled = state.moveSteps.length === 0;
  el.submitMoveBtn.disabled = !state.sessionId || state.moveSteps.length === 0 || state.animating;
  el.fromBarBtn.disabled = !state.position || state.animating;
  el.toOffBtn.disabled = !state.position || state.selectedFrom === null || state.animating;
  el.clearMoveBtn.disabled = el.clearMoveBtn.disabled || state.animating;
  el.undoStepBtn.disabled = el.undoStepBtn.disabled || state.animating;
  el.replayMoveBtn.disabled = state.animating || !state.lastReplay;
  el.toOffBtn.classList.toggle("valid-target-btn", offPoint !== null && validTargets.has(offPoint));
}

function renderLegalMoves() {
  el.legalMoves.innerHTML = "";
  for (const move of state.legalMoves) {
    const li = document.createElement("li");
    li.textContent = move.notation;
    li.title = "Click to auto-fill this move";
    li.addEventListener("click", () => {
      state.moveSteps = move.steps.map((s) => ({ from_point: s.from_point, to_point: s.to_point }));
      state.selectedFrom = null;
      renderMoveBuilder();
      renderBoard();
    });
    el.legalMoves.appendChild(li);
  }
}

function renderMoveLog() {
  if (!state.moveLog.length) {
    el.moveLog.textContent = "No moves yet.";
    return;
  }
  const lines = state.moveLog.map((entry, index) => {
    const note = entry.note ? ` (${entry.note})` : "";
    const dice = entry.dice ? ` [${entry.dice}]` : "";
    return `${index + 1}. ${entry.actor}: ${entry.notation}${dice}${note}`;
  });
  el.moveLog.textContent = lines.join("\n");
}

function formatMoveAnalysisSummary(analysis) {
  if (!analysis || !analysis.played_move || !analysis.best_move) {
    return "No move analysis available.";
  }
  const played = analysis.played_move;
  const best = analysis.best_move;
  const reasons = Array.isArray(played.why) && played.why.length ? played.why.join("; ") : "No notes.";
  return [
    `Played: ${played.notation}`,
    `Quality: ${played.quality} (equity ${played.equity.toFixed(3)}, loss ${played.delta_vs_best.toFixed(3)})`,
    `Best: ${best.notation} (equity ${best.equity.toFixed(3)})`,
    `Why: ${reasons}`,
  ].join("\n");
}

function refreshButtons() {
  const active = Boolean(state.sessionId);
  const blocked = state.animating;
  el.loadLegalBtn.disabled = !active || blocked;
  el.aiTurnBtn.disabled = !active || blocked;
  el.rollBtn.disabled = !active || blocked;
  el.sessionReportBtn.disabled = !active || blocked;
  el.closeSessionBtn.disabled = !active || blocked;
  el.cubeCheckBtn.disabled = !active || blocked;
  el.queueAnalysisBtn.disabled = !active || blocked;
  el.resumeSessionBtn.disabled = false;
  el.refreshSessionsBtn.disabled = blocked;
}

async function loadTrainingSummary() {
  try {
    const [dashboard, report] = await Promise.all([
      api(`/training/dashboard?profile_id=${encodeURIComponent(currentProfileId())}`),
      api(`/training/report?profile_id=${encodeURIComponent(currentProfileId())}`),
    ]);
    el.trainingSummary.textContent = `${JSON.stringify(dashboard, null, 2)}\n\nRecommendations:\n${JSON.stringify(report.recommendations, null, 2)}`;
  } catch (err) {
    el.trainingSummary.textContent = `Unable to load training summary: ${err.message}`;
  }
}

async function loadAnalysisJobs() {
  try {
    const profile = encodeURIComponent(currentProfileId());
    const [jobs, stats] = await Promise.all([
      api(`/analysis-jobs?profile_id=${profile}&limit=8`),
      api(`/analysis-jobs/stats?profile_id=${profile}`),
    ]);
    el.analysisJobs.textContent = `Stats:\\n${JSON.stringify(stats, null, 2)}\\n\\nJobs:\\n${JSON.stringify(jobs, null, 2)}`;
  } catch (err) {
    el.analysisJobs.textContent = `Unable to load jobs: ${err.message}`;
  }
}

function renderSessionPicker(sessions) {
  el.sessionPicker.innerHTML = "";
  if (!sessions.length) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "No sessions";
    el.sessionPicker.appendChild(empty);
    el.resumeSessionBtn.disabled = true;
    return;
  }

  for (const session of sessions) {
    const option = document.createElement("option");
    option.value = String(session.session_id);
    option.textContent = `#${session.session_id} ${session.status} moves:${session.move_count}`;
    el.sessionPicker.appendChild(option);
  }
  el.resumeSessionBtn.disabled = false;
}

async function loadSessionTurns(sessionId) {
  const data = await api(`/sessions/${sessionId}/turns?limit=300`);
  const turns = data.turns || [];
  state.moveLog = turns.map((turn) => {
    const actor = turn.actor === "ai" ? "AI" : "You";
    const noteParts = [`${turn.quality} ${Number(turn.equity_loss).toFixed(3)}`];
    if (turn.best_notation && turn.best_notation !== turn.played_notation) {
      noteParts.push(`best:${turn.best_notation}`);
    }
    return {
      actor,
      notation: turn.played_notation,
      dice: "",
      note: noteParts.join(" "),
    };
  });
  renderMoveLog();
}

async function loadSessionList() {
  try {
    const profile = encodeURIComponent(currentProfileId());
    const data = await api(`/sessions?profile_id=${profile}`);
    const sessions = data.sessions || [];
    renderSessionPicker(sessions);
  } catch (err) {
    notify(`Unable to load sessions: ${err.message}`, true);
  }
}

async function resumeSelectedSession() {
  const selected = Number(el.sessionPicker.value);
  if (!selected) {
    notify("Select a session to resume.", true);
    return;
  }
  try {
    const session = await api(`/sessions/${selected}`);
    if (session.status === "closed") {
      notify(`Session #${selected} is closed. Start a new one.`, true);
      return;
    }
    state.sessionId = session.session_id;
    state.position = session.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.moveLog = [];
    state.lastReplay = null;
    resetAnimationState();
    clearMoveHighlight(false);
    el.sessionStatus.textContent = `Session #${state.sessionId} (${session.status})`;
    refreshButtons();
    renderBoard();
    renderMoveBuilder();
    await loadSessionTurns(state.sessionId);
    await refreshLegalMoves(true);
    await loadTrainingSummary();
    await loadAnalysisJobs();
    notify(`Resumed session #${state.sessionId}.`);
  } catch (err) {
    notify(err.message, true);
  }
}

function onPointClick(point) {
  if (!state.position) return;
  if (state.selectedFrom === null) {
    chooseSource(point);
  } else {
    chooseDestination(point);
  }
}

async function newSession() {
  try {
    const position = {
      points: [-2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2],
      bar_white: 0,
      bar_black: 0,
      off_white: 0,
      off_black: 0,
      turn: "white",
      cube_value: 1,
      dice: currentDice(),
    };
    const created = await api("/sessions", {
      method: "POST",
      body: JSON.stringify({ initial_position: position, profile_id: currentProfileId() }),
    });
    state.sessionId = created.session_id;
    state.position = created.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.legalMoves = [];
    state.moveLog = [];
    state.lastReplay = null;
    resetAnimationState();
    clearMoveHighlight(false);
    el.sessionStatus.textContent = `Session #${state.sessionId} (${created.status})`;
    refreshButtons();
    renderBoard();
    renderMoveBuilder();
    renderMoveLog();
    notify("Session created.");
    await refreshLegalMoves(true);
    await loadTrainingSummary();
    await loadAnalysisJobs();
    await loadSessionList();
  } catch (err) {
    notify(err.message, true);
  }
}

async function loadLegalMoves() {
  await refreshLegalMoves(false);
}

async function submitMove() {
  if (!state.sessionId || state.moveSteps.length === 0 || !state.position) return;
  try {
    const startingPosition = clonePosition(state.position);
    const diceLabel = state.position ? `${state.position.dice[0]}-${state.position.dice[1]}` : "";
    const playedSteps = state.moveSteps.map((s) => ({ from_point: s.from_point, to_point: s.to_point }));
    const stepSummary = summarizeStepEvents(startingPosition, playedSteps);
    const notation = playedSteps.map((s) => `${s.from_point}/${s.to_point}`).join(" ");
    const played = await api(`/sessions/${state.sessionId}/play-turn`, {
      method: "POST",
      body: JSON.stringify({
        played_move: { notation, steps: playedSteps },
        record_training: true,
      }),
    });
    state.moveSteps = [];
    state.selectedFrom = null;
    state.moveLog.push({
      actor: "You",
      notation,
      dice: diceLabel,
      note: `${played.played_move.quality} ${played.played_move.delta_vs_best.toFixed(3)}${stepSummary.hits ? ` hits:${stepSummary.hits}` : ""}`,
    });
    renderMoveBuilder();
    renderMoveLog();
    setLastReplay(startingPosition, playedSteps, played.current_position);
    await animateMoveReplay(startingPosition, playedSteps, played.current_position);
    setMoveHighlightFromSteps(playedSteps);
    const summaryText = formatMoveAnalysisSummary(played.analysis);
    notify(stepSummary.hits ? `${summaryText}\nHits: ${stepSummary.hits}` : summaryText);
    await refreshLegalMoves(true);
    await loadTrainingSummary();
    await loadAnalysisJobs();
    if (el.autoAiToggle.checked && state.sessionId) {
      await aiTurn(false);
    }
  } catch (err) {
    notify(err.message, true);
  }
}

async function aiTurn(showNotify = true) {
  if (!state.sessionId || !state.position) return;
  try {
    const startingPosition = clonePosition(state.position);
    const played = await api(`/sessions/${state.sessionId}/ai-turn`, {
      method: "POST",
      body: JSON.stringify({ apply_move: true }),
    });
    const aiSteps = played.selected_play?.steps || [];
    const stepSummary = summarizeStepEvents(startingPosition, aiSteps);
    state.moveSteps = [];
    state.selectedFrom = null;
    state.moveLog.push({
      actor: "AI",
      notation: played.selected_play?.notation || played.selected_move.notation,
      dice: played.selected_move?.dice ? `${played.selected_move.dice[0]}-${played.selected_move.dice[1]}` : "",
      note: `${played.selected_move.quality} ${played.selected_move.delta_vs_best.toFixed(3)}${stepSummary.hits ? ` hits:${stepSummary.hits}` : ""}`,
    });
    renderMoveBuilder();
    renderMoveLog();
    setLastReplay(startingPosition, aiSteps, played.current_position);
    await animateMoveReplay(startingPosition, aiSteps, played.current_position);
    setMoveHighlightFromSteps(aiSteps);
    await refreshLegalMoves(true);
    if (showNotify) {
      notify(`AI played ${played.selected_move.notation}\n${JSON.stringify(played.selected_move, null, 2)}`);
    }
  } catch (err) {
    notify(err.message, true);
  }
}

async function rollDice() {
  if (!state.sessionId) return;
  try {
    const rolled = await api(`/sessions/${state.sessionId}/roll`, { method: "POST" });
    state.position = rolled.position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.lastReplay = null;
    resetAnimationState();
    clearMoveHighlight(false);
    renderMoveBuilder();
    el.die1.value = String(rolled.dice[0]);
    el.die2.value = String(rolled.dice[1]);
    await refreshLegalMoves(true);
    notify(`Rolled ${rolled.dice[0]}-${rolled.dice[1]}.`);
  } catch (err) {
    notify(err.message, true);
  }
}

async function closeSession() {
  if (!state.sessionId) return;
  try {
    const closed = await api(`/sessions/${state.sessionId}/close`, { method: "POST" });
    notify(`Session #${closed.session_id} closed.`);
    state.sessionId = null;
    state.position = null;
    state.legalMoves = [];
    state.moveSteps = [];
    state.selectedFrom = null;
    state.moveLog = [];
    state.lastReplay = null;
    resetAnimationState();
    clearMoveHighlight(false);
    el.sessionStatus.textContent = "No session";
    refreshButtons();
    renderBoard();
    renderMoveBuilder();
    renderMoveLog();
    renderLegalMoves();
    el.cubeFeedback.textContent = "No cube decision checked yet.";
    await loadAnalysisJobs();
    await loadSessionList();
  } catch (err) {
    notify(err.message, true);
  }
}

async function checkCubeDecision() {
  if (!state.position) return;
  try {
    const result = await api("/cube/decision", {
      method: "POST",
      body: JSON.stringify({
        position: state.position,
        action: el.cubeAction.value,
      }),
    });
    el.cubeFeedback.textContent = JSON.stringify(result, null, 2);
  } catch (err) {
    notify(err.message, true);
  }
}

function chooseFromBar() {
  if (!state.position) return;
  chooseSource(state.position.turn === "white" ? 25 : 0);
}

function chooseToOff() {
  if (!state.position || state.selectedFrom === null) return;
  const to = state.position.turn === "white" ? 0 : 25;
  chooseDestination(to);
}

function clearMove() {
  state.moveSteps = [];
  state.selectedFrom = null;
  clearDragState();
  clearMoveHighlight(false);
  renderMoveBuilder();
  renderBoard();
}

async function replayLastMove() {
  if (!state.lastReplay || state.animating) {
    return;
  }
  state.moveSteps = [];
  state.selectedFrom = null;
  clearDragState();
  renderMoveBuilder();
  await animateMoveReplay(
    state.lastReplay.startPosition,
    state.lastReplay.steps,
    state.lastReplay.finalPosition,
  );
  setMoveHighlightFromSteps(state.lastReplay.steps);
}

function undoMoveStep() {
  if (state.moveSteps.length === 0) {
    return;
  }
  state.moveSteps.pop();
  state.selectedFrom = null;
  clearDragState();
  renderMoveBuilder();
  renderBoard();
}

async function loadSessionReport() {
  if (!state.sessionId) return;
  try {
    const report = await api(`/sessions/${state.sessionId}/report?top_n=5`);
    notify(JSON.stringify(report, null, 2));
  } catch (err) {
    notify(err.message, true);
  }
}

function renderDrillStatus() {
  if (!state.currentDrill) {
    el.drillStatus.textContent = "No drill loaded.";
    el.submitDrillBtn.disabled = true;
    return;
  }
  el.drillStatus.textContent = JSON.stringify(
    {
      review_id: state.currentDrill.review_id,
      leak_category: state.currentDrill.leak_category,
      equity_loss: state.currentDrill.equity_loss,
      played_notation: state.currentDrill.played_notation,
    },
    null,
    2,
  );
  el.submitDrillBtn.disabled = false;
}

async function loadDrill() {
  try {
    const data = await api(
      `/training/drills?limit=1&profile_id=${encodeURIComponent(currentProfileId())}`,
    );
    if (!data.drills.length) {
      notify("No drills available yet. Record some rated moves first.", true);
      state.currentDrill = null;
      renderDrillStatus();
      return;
    }
    state.currentDrill = data.drills[0];
    state.position = state.currentDrill.position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.moveLog = [];
    state.lastReplay = null;
    resetAnimationState();
    clearMoveHighlight(false);
    renderMoveBuilder();
    renderMoveLog();
    await refreshLegalMoves(true);
    renderDrillStatus();
    notify("Drill loaded. Enter your best move notation and submit.");
  } catch (err) {
    notify(err.message, true);
  }
}

async function submitDrillAttempt() {
  if (!state.currentDrill) return;
  const chosen = el.drillAnswer.value.trim();
  if (!chosen) {
    notify("Enter a move notation before submitting.", true);
    return;
  }
  try {
    const result = await api("/training/drills/attempt", {
      method: "POST",
      body: JSON.stringify({
        review_id: state.currentDrill.review_id,
        chosen_notation: chosen,
        profile_id: currentProfileId(),
      }),
    });
    notify(JSON.stringify(result, null, 2));
    await loadTrainingSummary();
  } catch (err) {
    notify(err.message, true);
  }
}

async function queueCurrentPositionAnalysis() {
  if (!state.position) return;
  try {
    const created = await api("/analysis-jobs", {
      method: "POST",
      body: JSON.stringify({
        profile_id: currentProfileId(),
        analysis_mode: el.analysisMode.value,
        position: state.position,
      }),
    });
    notify(`Queued analysis job #${created.job_id}.`);
    await loadAnalysisJobs();
  } catch (err) {
    notify(err.message, true);
  }
}

async function runNextAnalysisJob() {
  try {
    const ran = await api(
      `/analysis-jobs/run-next?profile_id=${encodeURIComponent(currentProfileId())}`,
      { method: "POST" },
    );
    notify(`Ran analysis job #${ran.job_id} (${ran.status}).`);
    await loadAnalysisJobs();
  } catch (err) {
    notify(err.message, true);
  }
}

async function retryLatestJob() {
  try {
    const jobs = await api(`/analysis-jobs?profile_id=${encodeURIComponent(currentProfileId())}&limit=1`);
    if (!jobs.jobs.length) {
      notify("No jobs available to retry.", true);
      return;
    }
    const latest = jobs.jobs[0];
    const retried = await api(`/analysis-jobs/${latest.job_id}/retry`, { method: "POST" });
    notify(`Job #${retried.job_id} reset to pending.`);
    await loadAnalysisJobs();
  } catch (err) {
    notify(err.message, true);
  }
}

async function cleanupFinishedJobs() {
  try {
    const cleaned = await api(
      `/analysis-jobs/cleanup?profile_id=${encodeURIComponent(currentProfileId())}`,
      { method: "POST" },
    );
    notify(`Cleaned ${cleaned.deleted} finished jobs.`);
    await loadAnalysisJobs();
  } catch (err) {
    notify(err.message, true);
  }
}

el.newSessionBtn.addEventListener("click", newSession);
el.loadLegalBtn.addEventListener("click", loadLegalMoves);
el.submitMoveBtn.addEventListener("click", submitMove);
el.aiTurnBtn.addEventListener("click", aiTurn);
el.rollBtn.addEventListener("click", rollDice);
el.fromBarBtn.addEventListener("click", chooseFromBar);
el.toOffBtn.addEventListener("click", chooseToOff);
el.undoStepBtn.addEventListener("click", undoMoveStep);
el.clearMoveBtn.addEventListener("click", clearMove);
el.replayMoveBtn.addEventListener("click", replayLastMove);
el.sessionReportBtn.addEventListener("click", loadSessionReport);
el.closeSessionBtn.addEventListener("click", closeSession);
el.refreshSessionsBtn.addEventListener("click", loadSessionList);
el.resumeSessionBtn.addEventListener("click", resumeSelectedSession);
el.cubeCheckBtn.addEventListener("click", checkCubeDecision);
el.loadDrillBtn.addEventListener("click", loadDrill);
el.submitDrillBtn.addEventListener("click", submitDrillAttempt);
el.queueAnalysisBtn.addEventListener("click", queueCurrentPositionAnalysis);
el.runNextAnalysisBtn.addEventListener("click", runNextAnalysisJob);
el.retryLatestJobBtn.addEventListener("click", retryLatestJob);
el.cleanupJobsBtn.addEventListener("click", cleanupFinishedJobs);
el.profileId.addEventListener("change", async () => {
  savePreferences();
  await loadTrainingSummary();
  await loadAnalysisJobs();
  await loadSessionList();
});
el.autoAiToggle.addEventListener("change", savePreferences);
el.animationMs.addEventListener("change", savePreferences);
el.toOffBtn.addEventListener("dragover", onOffDragOver);
el.toOffBtn.addEventListener("drop", onOffDrop);
el.toOffBtn.addEventListener("touchend", (event) => {
  if (!state.touchDragging) return;
  event.preventDefault();
  onOffDrop(event);
}, { passive: false });

window.addEventListener("keydown", (event) => {
  const tag = event.target && event.target.tagName ? event.target.tagName.toLowerCase() : "";
  const typing = tag === "input" || tag === "textarea" || tag === "select";
  if (typing) {
    return;
  }

  if (event.key === "Enter" && !el.submitMoveBtn.disabled) {
    event.preventDefault();
    submitMove();
    return;
  }
  if (event.key === "Backspace" && !el.undoStepBtn.disabled) {
    event.preventDefault();
    undoMoveStep();
    return;
  }
  if (event.key === "Escape" && !el.clearMoveBtn.disabled) {
    event.preventDefault();
    clearMove();
  }
});

refreshButtons();
loadPreferences();
renderBoard();
renderMoveBuilder();
renderMoveLog();
renderDrillStatus();
loadTrainingSummary();
loadAnalysisJobs();
loadSessionList();
