# Gammondator Project Overview

## Mission
Build a backgammon training platform that gives immediate, high-quality feedback on player decisions during real gameplay.

Gammondator is intended to be the backgammon equivalent of poker GTO trainers: play hands (games), get precise move quality feedback, and learn *why* better alternatives are stronger.

## Problem We Are Solving
Most analysis tools require users to manually set up a position and run analysis. That workflow is too slow for deliberate training during active play.

Gammondator solves this by running in a live game loop:
- User plays against an AI opponent.
- Every user move is evaluated immediately.
- The system shows whether the move was good, how much equity was lost (if any), and the best alternative with explanation.

## Product Goals
1. Real-time move coaching without interrupting gameplay.
2. Actionable explanations, not just numeric equity outputs.
3. Personalized improvement loop using mistake history and drills.
4. Engine-agnostic architecture so strong analyzers can be swapped in.

## Non-Goals (Current Phase)
- Building a world-class solver from scratch.
- Full production multiplayer platform.
- Advanced visual polish before core training loop is reliable.

## Current State (Implemented)
- FastAPI backend service.
- Endpoints:
  - `GET /health`
  - `GET /analyzer`
  - `POST /analyze-move`
  - `POST /choose-ai-move`
  - `POST /legal-moves`
  - `POST /choose-ai-move-from-position`
  - `POST /rate-played-move`
- Strict input/output schemas for position and move analysis.
- Heuristic baseline analyzer with move quality classification.
- Explanation layer based on structural/racing features.
- Backend abstraction with configurable analyzer backend.
- Server-side legal move generation from position + dice (including bar entry and bearing off rules).
- Server-side played-move rating from position + move (no client candidate list required).
- GNU Backgammon bridge contract support with fallback to heuristic backend.
- Local bridge stub script for integration testing.
- Automated tests for API + backend behavior.

## Planned Features

### Phase 1: Core Training Loop (MVP)
- Human vs AI gameplay loop integration.
- Legal move generation service.
- Immediate post-move evaluation and ranking.
- Top move suggestions with equity deltas.
- Basic move quality labels (`excellent`, `good`, `inaccuracy`, `mistake`, `blunder`).

### Phase 2: Better Explanations
- Position feature extraction expansion:
  - shot risk
  - blots
  - prime structure
  - anchors
  - race/timing
- Better reason templates tied to tactical and strategic themes.
- Post-game summary of top mistakes and recurring leak categories.

### Phase 3: Personalized Training
- Persistent user profile and game history.
- Mistake database with tagging and severity.
- Drill mode for repeated weak patterns.
- Progress metrics over time (average equity loss, blunder rate, category trends).

### Phase 4: Strong Engine Integration
- Production GNU Backgammon bridge process.
- Configurable rollout depth and latency/quality trade-offs.
- Optional hybrid pipeline:
  - fast heuristic for immediate UX
  - deferred deep analysis for post-game reports

### Phase 5: Match Strategy Layer
- Cube decision coaching.
- Match-score-aware recommendations.
- Score-context mistakes and equity impact reporting.

## Architecture Direction

### Backend
- Python FastAPI service as orchestration layer.
- Analyzer backend interface with pluggable providers:
  - heuristic backend (always available)
  - GNUbg bridge backend (strong analysis path)
- Stable response contract for front-end independence.

### Frontend (Planned)
- Interactive board UI for live play.
- Move input and candidate list generation.
- Inline feedback panel for move quality + explanation.
- Review mode for mistakes and best lines.

### Data Model (Planned)
- `games`
- `positions`
- `played_moves`
- `candidate_evaluations`
- `mistake_tags`
- `training_sessions`

## Key Metrics
- Average equity loss per decision.
- Blunder frequency.
- Improvement trend over recent N games.
- Time-to-feedback latency per move.
- Explanation usefulness rating (user feedback loop).

## Quality and Reliability Principles
- Keep the API contract stable as analyzers evolve.
- Ensure graceful fallback when external engine is unavailable.
- Keep tests green before adding major functionality.
- Favor deterministic behavior in MVP paths.

## Immediate Next Steps
1. Build the first real GNUbg bridge process (replace stub behavior).
2. Add a lightweight game session model and persistence.
3. Scaffold a minimal web UI to play against AI and call analysis endpoints.
4. Add post-game report endpoint summarizing mistakes by severity/category.
5. Add cube-decision analysis path for match play.

## Project Conventions
- Branch naming: `codex/*`.
- Keep generated artifacts out of git via `.gitignore`.
- Run tests via project virtualenv:
  - `.venv/bin/python -m pytest -q`
