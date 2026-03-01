const state = {
  sessionId: null,
  position: null,
  legalMoves: [],
  moveSteps: [],
  selectedFrom: null,
  currentDrill: null,
};

const el = {
  die1: document.getElementById("die1"),
  die2: document.getElementById("die2"),
  profileId: document.getElementById("profileId"),
  newSessionBtn: document.getElementById("newSessionBtn"),
  loadLegalBtn: document.getElementById("loadLegalBtn"),
  aiTurnBtn: document.getElementById("aiTurnBtn"),
  rollBtn: document.getElementById("rollBtn"),
  sessionReportBtn: document.getElementById("sessionReportBtn"),
  closeSessionBtn: document.getElementById("closeSessionBtn"),
  loadDrillBtn: document.getElementById("loadDrillBtn"),
  sessionStatus: document.getElementById("sessionStatus"),
  boardGrid: document.getElementById("boardGrid"),
  turnLabel: document.getElementById("turnLabel"),
  barOffLabel: document.getElementById("barOffLabel"),
  cubeLabel: document.getElementById("cubeLabel"),
  fromBarBtn: document.getElementById("fromBarBtn"),
  toOffBtn: document.getElementById("toOffBtn"),
  clearMoveBtn: document.getElementById("clearMoveBtn"),
  currentMove: document.getElementById("currentMove"),
  submitMoveBtn: document.getElementById("submitMoveBtn"),
  legalMoves: document.getElementById("legalMoves"),
  feedback: document.getElementById("feedback"),
  trainingSummary: document.getElementById("trainingSummary"),
  cubeAction: document.getElementById("cubeAction"),
  cubeCheckBtn: document.getElementById("cubeCheckBtn"),
  cubeFeedback: document.getElementById("cubeFeedback"),
  drillStatus: document.getElementById("drillStatus"),
  drillAnswer: document.getElementById("drillAnswer"),
  submitDrillBtn: document.getElementById("submitDrillBtn"),
};

function notify(text, isError = false) {
  el.feedback.textContent = isError ? `Error: ${text}` : text;
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

function pointLabel(point) {
  return `P${point}`;
}

function renderBoard() {
  if (!state.position) {
    el.boardGrid.innerHTML = "";
    return;
  }

  el.turnLabel.textContent = `Turn: ${state.position.turn}`;
  el.barOffLabel.textContent = `Bar W/B: ${state.position.bar_white}/${state.position.bar_black} | Off W/B: ${state.position.off_white}/${state.position.off_black}`;
  el.cubeLabel.textContent = `Cube: ${state.position.cube_value} | Dice: ${state.position.dice[0]}-${state.position.dice[1]}`;

  el.boardGrid.innerHTML = "";
  for (let point = 24; point >= 1; point -= 1) {
    const idx = point - 1;
    const value = state.position.points[idx];
    const text = value === 0 ? "empty" : value > 0 ? `W ${value}` : `B ${Math.abs(value)}`;
    const btn = document.createElement("button");
    btn.className = `point-btn${state.selectedFrom === point ? " selected" : ""}`;
    btn.innerHTML = `<strong>${pointLabel(point)}</strong><br/>${text}`;
    btn.addEventListener("click", () => onPointClick(point));
    el.boardGrid.appendChild(btn);
  }
}

function renderMoveBuilder() {
  if (state.moveSteps.length === 0) {
    el.currentMove.textContent = "No move selected";
  } else {
    const text = state.moveSteps.map((s) => `${s.from_point}/${s.to_point}`).join(" ");
    el.currentMove.textContent = text;
  }
  el.clearMoveBtn.disabled = state.moveSteps.length === 0;
  el.submitMoveBtn.disabled = !state.sessionId || state.moveSteps.length === 0;
  el.fromBarBtn.disabled = !state.position;
  el.toOffBtn.disabled = !state.position || state.selectedFrom === null;
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

function refreshButtons() {
  const active = Boolean(state.sessionId);
  el.loadLegalBtn.disabled = !active;
  el.aiTurnBtn.disabled = !active;
  el.rollBtn.disabled = !active;
  el.sessionReportBtn.disabled = !active;
  el.closeSessionBtn.disabled = !active;
  el.cubeCheckBtn.disabled = !active;
}

async function loadTrainingSummary() {
  try {
    const [summary, leaks, drillSummary] = await Promise.all([
      api(`/training/summary?profile_id=${encodeURIComponent(currentProfileId())}`),
      api(`/training/leaks?profile_id=${encodeURIComponent(currentProfileId())}`),
      api(`/training/drills/summary?profile_id=${encodeURIComponent(currentProfileId())}`),
    ]);
    el.trainingSummary.textContent = `${JSON.stringify(summary, null, 2)}\n\nLeaks:\n${JSON.stringify(leaks, null, 2)}\n\nDrills:\n${JSON.stringify(drillSummary, null, 2)}`;
  } catch (err) {
    el.trainingSummary.textContent = `Unable to load training summary: ${err.message}`;
  }
}

function onPointClick(point) {
  if (!state.position) return;
  if (state.selectedFrom === null) {
    state.selectedFrom = point;
  } else {
    state.moveSteps.push({ from_point: state.selectedFrom, to_point: point });
    state.selectedFrom = null;
  }
  renderMoveBuilder();
  renderBoard();
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
    el.sessionStatus.textContent = `Session #${state.sessionId} (${created.status})`;
    refreshButtons();
    renderBoard();
    renderMoveBuilder();
    renderLegalMoves();
    notify("Session created.");
    await loadTrainingSummary();
  } catch (err) {
    notify(err.message, true);
  }
}

async function loadLegalMoves() {
  try {
    const data = await api("/legal-moves", {
      method: "POST",
      body: JSON.stringify({ position: state.position }),
    });
    state.legalMoves = data.moves;
    renderLegalMoves();
    notify(`Loaded ${data.moves.length} legal moves.`);
  } catch (err) {
    notify(err.message, true);
  }
}

async function submitMove() {
  if (!state.sessionId || state.moveSteps.length === 0) return;
  try {
    const notation = state.moveSteps.map((s) => `${s.from_point}/${s.to_point}`).join(" ");
    const played = await api(`/sessions/${state.sessionId}/play-turn`, {
      method: "POST",
      body: JSON.stringify({
        played_move: { notation, steps: state.moveSteps },
        record_training: true,
      }),
    });
    state.position = played.current_position;
    state.moveSteps = [];
    state.selectedFrom = null;
    state.legalMoves = [];
    renderBoard();
    renderMoveBuilder();
    renderLegalMoves();
    notify(JSON.stringify(played.analysis, null, 2));
    await loadTrainingSummary();
  } catch (err) {
    notify(err.message, true);
  }
}

async function aiTurn() {
  if (!state.sessionId) return;
  try {
    const played = await api(`/sessions/${state.sessionId}/ai-turn`, {
      method: "POST",
      body: JSON.stringify({ apply_move: true }),
    });
    state.position = played.current_position;
    state.legalMoves = [];
    renderBoard();
    renderLegalMoves();
    notify(`AI played ${played.selected_move.notation}\n${JSON.stringify(played.selected_move, null, 2)}`);
  } catch (err) {
    notify(err.message, true);
  }
}

async function rollDice() {
  if (!state.sessionId) return;
  try {
    const rolled = await api(`/sessions/${state.sessionId}/roll`, { method: "POST" });
    state.position = rolled.position;
    el.die1.value = String(rolled.dice[0]);
    el.die2.value = String(rolled.dice[1]);
    renderBoard();
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
    state.legalMoves = [];
    state.moveSteps = [];
    state.selectedFrom = null;
    el.sessionStatus.textContent = "No session";
    refreshButtons();
    renderMoveBuilder();
    renderLegalMoves();
    el.cubeFeedback.textContent = "No cube decision checked yet.";
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
  state.selectedFrom = state.position.turn === "white" ? 25 : 0;
  renderBoard();
  renderMoveBuilder();
}

function chooseToOff() {
  if (!state.position || state.selectedFrom === null) return;
  const to = state.position.turn === "white" ? 0 : 25;
  state.moveSteps.push({ from_point: state.selectedFrom, to_point: to });
  state.selectedFrom = null;
  renderMoveBuilder();
  renderBoard();
}

function clearMove() {
  state.moveSteps = [];
  state.selectedFrom = null;
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
    state.legalMoves = [];
    state.moveSteps = [];
    state.selectedFrom = null;
    renderBoard();
    renderMoveBuilder();
    renderLegalMoves();
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

el.newSessionBtn.addEventListener("click", newSession);
el.loadLegalBtn.addEventListener("click", loadLegalMoves);
el.submitMoveBtn.addEventListener("click", submitMove);
el.aiTurnBtn.addEventListener("click", aiTurn);
el.rollBtn.addEventListener("click", rollDice);
el.fromBarBtn.addEventListener("click", chooseFromBar);
el.toOffBtn.addEventListener("click", chooseToOff);
el.clearMoveBtn.addEventListener("click", clearMove);
el.sessionReportBtn.addEventListener("click", loadSessionReport);
el.closeSessionBtn.addEventListener("click", closeSession);
el.cubeCheckBtn.addEventListener("click", checkCubeDecision);
el.loadDrillBtn.addEventListener("click", loadDrill);
el.submitDrillBtn.addEventListener("click", submitDrillAttempt);

refreshButtons();
renderBoard();
renderMoveBuilder();
renderDrillStatus();
loadTrainingSummary();
