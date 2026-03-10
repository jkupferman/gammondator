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

export function renderDiceReadout(d1, d2) {
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

function formatMoveAnalysisSummary(analysis, lastHumanMetricValue, lastHumanMetricKind) {
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
  const hasWinPct = typeof played.win_pct === "number";
  const currentMetricKind = hasWinPct ? "win_pct" : "equity";
  const currentMetricValue = hasWinPct
    ? Number(played.win_pct || 0) * 100.0
    : Number(played.equity || 0);
  const metricDelta =
    lastHumanMetricValue === null || lastHumanMetricKind !== currentMetricKind
      ? null
      : currentMetricValue - lastHumanMetricValue;
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
  const nextStepLine = isOptimal ? null : `Takeaway: ${nextStep}`;
  return {
    quality: played.quality,
    qualityTitle: headline,
    playedNotation: playedDisplay,
    bestLine: bestDisplay,
    equityLossLine: `Equity loss: ${loss.toFixed(3)}. ${lossHint}`,
    metricKind: currentMetricKind,
    metricValue: currentMetricValue,
    metricDelta,
    whyLine: `${whyPrefix}: ${firstReason}`,
    nextStepLine,
  };
}

export function buildAnalysisFeedback(
  analysis,
  lastHumanMetricValue,
  lastHumanMetricKind,
  aiSummary = "",
) {
  const summary = formatMoveAnalysisSummary(analysis, lastHumanMetricValue, lastHumanMetricKind);
  if (!summary) {
    return {
      ok: false,
      text: "No move analysis available.",
      nextHumanMetricValue: lastHumanMetricValue,
      nextHumanMetricKind: lastHumanMetricKind,
    };
  }

  const qualityClass = `quality-${summary.quality || "good"}`;
  const hasDelta = summary.metricDelta !== null;
  const precision = summary.metricKind === "win_pct" ? 1 : 3;
  const flatThreshold = summary.metricKind === "win_pct" ? 0.05 : 0.001;
  const normalizedDelta = hasDelta ? Number(summary.metricDelta.toFixed(precision)) : null;
  const isFlatDelta = normalizedDelta !== null && Math.abs(normalizedDelta) < flatThreshold;
  const deltaText =
    !hasDelta
      ? ""
      : isFlatDelta
        ? "(no change)"
        : summary.metricKind === "win_pct"
          ? `(${normalizedDelta >= 0 ? "+" : ""}${normalizedDelta.toFixed(1)}%)`
          : `(${normalizedDelta >= 0 ? "+" : ""}${normalizedDelta.toFixed(3)})`;
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
    escapeHtml(summary.equityLossLine),
    `${summary.metricKind === "win_pct" ? "Win Pct" : "Equity"}: ${
      summary.metricKind === "win_pct"
        ? `${summary.metricValue.toFixed(1)}%`
        : summary.metricValue.toFixed(3)
    }` +
      (deltaText ? ` <span class="feedback-win-delta ${deltaClass}">${escapeHtml(deltaText)}</span>` : ""),
    escapeHtml(summary.whyLine),
  ];

  if (summary.nextStepLine) {
    lines.push(escapeHtml(summary.nextStepLine));
  }
  if (aiSummary) {
    lines.push("");
    lines.push(escapeHtml(aiSummary));
  }

  return {
    ok: true,
    html: lines.join("\n"),
    nextHumanMetricValue: summary.metricValue,
    nextHumanMetricKind: summary.metricKind,
  };
}

export function formatTipSummary(selectedMove, suggestion) {
  if (!selectedMove || !suggestion) {
    return "No tip available right now.";
  }
  const reasons = Array.isArray(selectedMove.why) && selectedMove.why.length ? selectedMove.why : [];
  const leadReason = reasons[0] ? `\nReason: ${reasons[0]}` : "";
  return `Tip: consider ${suggestion.notation}\nThis is rated ${selectedMove.quality} (equity ${selectedMove.equity.toFixed(3)}).${leadReason}`;
}
