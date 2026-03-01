import os
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analysis import apply_move_to_position
from app.analysis_jobs import AnalysisJobStore
from app.backends import BackendUnavailableError, load_backend
from app.cube import evaluate_cube_decision
from app.movegen import generate_legal_moves, is_legal_move, legal_move_signatures, move_signature
from app.session_store import SessionStore
from app.schemas import (
    AnalyzePositionRequest,
    AnalyzePositionResponse,
    AnalyzeMoveRequest,
    AnalyzeMoveResponse,
    AnalyzerInfoResponse,
    AnalysisJobCreateRequest,
    AnalysisJobBatchRunResponse,
    AnalysisJobListResponse,
    AnalysisJobResponse,
    ChooseAIMoveRequest,
    ChooseAIMoveFromPositionRequest,
    ChooseAIMoveResponse,
    LegalMovesRequest,
    LegalMovesResponse,
    RatePlayedMoveRequest,
    RatePlayedMoveRecordedResponse,
    CubeDecisionRequest,
    CubeDecisionResponse,
    SessionCreateRequest,
    SessionAIMoveRequest,
    SessionAIMoveResponse,
    SessionCloseResponse,
    SessionRollResponse,
    SessionReportResponse,
    SessionPlayTurnRequest,
    SessionPlayTurnResponse,
    SessionListResponse,
    SessionStateResponse,
    TrainingMistakesResponse,
    TrainingLeaksResponse,
    TrainingDrillAttemptRequest,
    TrainingDrillAttemptResponse,
    TrainingDrillsResponse,
    TrainingDrillSummaryResponse,
    TrainingDashboardResponse,
    TrainingSummaryResponse,
)
from app.training_store import TrainingStore

app = FastAPI(title="Gammondator API", version="0.1.0")
runtime = load_backend()
training_store = TrainingStore(db_path=os.getenv("GAMMONDATOR_DB_PATH", "gammondator.db"))
session_store = SessionStore(db_path=os.getenv("GAMMONDATOR_DB_PATH", "gammondator.db"))
analysis_store = AnalysisJobStore(db_path=os.getenv("GAMMONDATOR_DB_PATH", "gammondator.db"))
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "backend": runtime.backend.name}


@app.get("/")
def web_index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/analyzer", response_model=AnalyzerInfoResponse)
def analyzer_info() -> AnalyzerInfoResponse:
    return AnalyzerInfoResponse(
        backend=runtime.backend.name,
        fallback_active=runtime.fallback_active,
        details=runtime.details,
    )


def _job_to_response(job: dict[str, object]) -> AnalysisJobResponse:
    result_payload = job.get("result")
    result = AnalyzeMoveResponse.model_validate(result_payload) if isinstance(result_payload, dict) else None
    return AnalysisJobResponse(
        job_id=int(job["job_id"]),
        profile_id=str(job["profile_id"]),
        status=str(job["status"]),
        created_at=str(job["created_at"]),
        updated_at=str(job["updated_at"]),
        error=str(job["error"]) if job.get("error") else None,
        result=result,
    )


def _run_analysis_job(job_id: int) -> AnalysisJobResponse:
    job = analysis_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"analysis job {job_id} not found")
    if str(job["status"]) == "completed":
        return _job_to_response(job)

    analysis_store.mark_running(job_id)
    job = analysis_store.get_job(job_id)
    assert job is not None
    request_payload = AnalysisJobCreateRequest.model_validate(job["request"])

    try:
        if request_payload.candidate_moves:
            candidate_moves = request_payload.candidate_moves
            _validate_candidate_moves(request_payload.position, candidate_moves)
            played_move = request_payload.played_move or candidate_moves[0]
            if not is_legal_move(request_payload.position, played_move):
                raise ValueError("played_move is not legal for this position/dice")
            analyze_request = AnalyzeMoveRequest(
                position=request_payload.position,
                played_move=played_move,
                candidate_moves=candidate_moves,
            )
        else:
            legal_moves = generate_legal_moves(request_payload.position)
            if not legal_moves:
                raise ValueError("no legal moves available")
            played_move = request_payload.played_move or legal_moves[0]
            if not is_legal_move(request_payload.position, played_move):
                raise ValueError("played_move is not legal for this position/dice")
            analyze_request = AnalyzeMoveRequest(
                position=request_payload.position,
                played_move=played_move,
                candidate_moves=legal_moves,
            )

        result = runtime.analyze_move(analyze_request)
        analysis_store.mark_completed(job_id, result.model_dump_json())
    except (BackendUnavailableError, ValueError) as exc:
        analysis_store.mark_failed(job_id, str(exc))

    final_job = analysis_store.get_job(job_id)
    assert final_job is not None
    return _job_to_response(final_job)


@app.post("/analysis-jobs", response_model=AnalysisJobResponse)
def create_analysis_job_endpoint(payload: AnalysisJobCreateRequest) -> AnalysisJobResponse:
    job_id = analysis_store.create_job(payload)
    job = analysis_store.get_job(job_id)
    assert job is not None
    return _job_to_response(job)


@app.get("/analysis-jobs", response_model=AnalysisJobListResponse)
def list_analysis_jobs_endpoint(
    profile_id: str = "default",
    status: str | None = None,
    limit: int = 50,
) -> AnalysisJobListResponse:
    jobs = analysis_store.list_jobs(profile_id=profile_id, status=status, limit=limit)
    return AnalysisJobListResponse(jobs=[_job_to_response(job) for job in jobs])


@app.get("/analysis-jobs/{job_id}", response_model=AnalysisJobResponse)
def get_analysis_job_endpoint(job_id: int) -> AnalysisJobResponse:
    job = analysis_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"analysis job {job_id} not found")
    return _job_to_response(job)


@app.post("/analysis-jobs/{job_id}/run", response_model=AnalysisJobResponse)
def run_analysis_job_endpoint(job_id: int) -> AnalysisJobResponse:
    return _run_analysis_job(job_id)


@app.post("/analysis-jobs/run-next", response_model=AnalysisJobResponse)
def run_next_analysis_job_endpoint(profile_id: str | None = None) -> AnalysisJobResponse:
    next_job = analysis_store.next_pending_job(profile_id=profile_id)
    if next_job is None:
        raise HTTPException(status_code=404, detail="no pending analysis jobs")
    return _run_analysis_job(int(next_job["job_id"]))


@app.post("/analysis-jobs/run-batch", response_model=AnalysisJobBatchRunResponse)
def run_batch_analysis_jobs_endpoint(
    profile_id: str | None = None,
    limit: int = 10,
) -> AnalysisJobBatchRunResponse:
    safe_limit = max(1, min(limit, 200))
    processed = 0
    completed = 0
    failed = 0
    job_ids: list[int] = []

    for _ in range(safe_limit):
        next_job = analysis_store.next_pending_job(profile_id=profile_id)
        if next_job is None:
            break
        job_id = int(next_job["job_id"])
        result = _run_analysis_job(job_id)
        job_ids.append(job_id)
        processed += 1
        if result.status == "completed":
            completed += 1
        elif result.status == "failed":
            failed += 1

    return AnalysisJobBatchRunResponse(
        processed=processed,
        completed=completed,
        failed=failed,
        job_ids=job_ids,
    )


@app.post("/sessions", response_model=SessionStateResponse)
def create_session_endpoint(payload: SessionCreateRequest) -> SessionStateResponse:
    created = session_store.create_session(payload.initial_position, profile_id=payload.profile_id)
    return SessionStateResponse(
        session_id=int(created["session_id"]),
        profile_id=str(created["profile_id"]),
        status=str(created["status"]),
        move_count=int(created["move_count"]),
        current_position=created["current_position"],
    )


@app.get("/sessions", response_model=SessionListResponse)
def list_sessions_endpoint(profile_id: str = "default", status: str | None = None) -> SessionListResponse:
    sessions = session_store.list_sessions(profile_id=profile_id, status=status)
    return SessionListResponse(sessions=[SessionStateResponse.model_validate(s) for s in sessions])


@app.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session_endpoint(session_id: int) -> SessionStateResponse:
    state = session_store.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    return SessionStateResponse(
        session_id=int(state["session_id"]),
        profile_id=str(state["profile_id"]),
        status=str(state["status"]),
        move_count=int(state["move_count"]),
        current_position=state["current_position"],
    )


@app.post("/sessions/{session_id}/close", response_model=SessionCloseResponse)
def close_session_endpoint(session_id: int) -> SessionCloseResponse:
    try:
        closed = session_store.close_session(session_id)
        return SessionCloseResponse(session_id=int(closed["session_id"]), status=str(closed["status"]))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/roll", response_model=SessionRollResponse)
def roll_session_dice_endpoint(session_id: int) -> SessionRollResponse:
    state = session_store.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    dice = (random.randint(1, 6), random.randint(1, 6))
    pos = state["current_position"]
    rolled_position = pos.model_copy(update={"dice": dice})
    try:
        updated = session_store.set_position(session_id=session_id, position=rolled_position)
        return SessionRollResponse(
            session_id=int(updated["session_id"]),
            dice=dice,
            position=updated["current_position"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/sessions/{session_id}/report", response_model=SessionReportResponse)
def session_report_endpoint(session_id: int, top_n: int = 5) -> SessionReportResponse:
    try:
        report = session_store.session_report(session_id=session_id, top_n=top_n)
        return SessionReportResponse.model_validate(report)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/analyze-move", response_model=AnalyzeMoveResponse)
def analyze_move_endpoint(payload: AnalyzeMoveRequest) -> AnalyzeMoveResponse:
    try:
        _validate_candidate_moves(payload.position, payload.candidate_moves)
        if not is_legal_move(payload.position, payload.played_move):
            raise HTTPException(status_code=400, detail="played_move is not legal for this position/dice")
        return runtime.analyze_move(payload)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/choose-ai-move", response_model=ChooseAIMoveResponse)
def choose_ai_move_endpoint(payload: ChooseAIMoveRequest) -> ChooseAIMoveResponse:
    try:
        _validate_candidate_moves(payload.position, payload.candidate_moves)
        analyzed = runtime.analyze_move(
            AnalyzeMoveRequest(
                position=payload.position,
                played_move=payload.candidate_moves[0],
                candidate_moves=payload.candidate_moves,
            )
        )
        return ChooseAIMoveResponse(selected_move=analyzed.best_move, top_moves=analyzed.top_moves)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/legal-moves", response_model=LegalMovesResponse)
def legal_moves_endpoint(payload: LegalMovesRequest) -> LegalMovesResponse:
    try:
        return LegalMovesResponse(moves=generate_legal_moves(payload.position))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/choose-ai-move-from-position", response_model=ChooseAIMoveResponse)
def choose_ai_move_from_position_endpoint(
    payload: ChooseAIMoveFromPositionRequest,
) -> ChooseAIMoveResponse:
    try:
        analyzed = _analyze_position(AnalyzePositionRequest(position=payload.position))
        return ChooseAIMoveResponse(selected_move=analyzed.best_move, top_moves=analyzed.top_moves)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _rate_played_move(payload: RatePlayedMoveRequest) -> AnalyzeMoveResponse:
    legal_moves = generate_legal_moves(payload.position)
    if not legal_moves:
        raise HTTPException(status_code=400, detail="no legal moves available")

    if move_signature(payload.played_move) not in legal_move_signatures(payload.position):
        raise HTTPException(status_code=400, detail="played_move is not legal for this position/dice")

    return runtime.analyze_move(
        AnalyzeMoveRequest(
            position=payload.position,
            played_move=payload.played_move,
            candidate_moves=legal_moves,
        )
    )


def _analyze_position(payload: AnalyzePositionRequest) -> AnalyzeMoveResponse:
    legal_moves = generate_legal_moves(payload.position)
    if not legal_moves:
        raise HTTPException(status_code=400, detail="no legal moves available")

    return runtime.analyze_move(
        AnalyzeMoveRequest(
            position=payload.position,
            played_move=legal_moves[0],
            candidate_moves=legal_moves,
        )
    )


@app.post("/rate-played-move", response_model=AnalyzeMoveResponse)
def rate_played_move_endpoint(payload: RatePlayedMoveRequest) -> AnalyzeMoveResponse:
    try:
        return _rate_played_move(payload)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/rate-played-move-and-record", response_model=RatePlayedMoveRecordedResponse)
def rate_played_move_and_record_endpoint(
    payload: RatePlayedMoveRequest,
) -> RatePlayedMoveRecordedResponse:
    try:
        analysis = _rate_played_move(payload)
        review_id = training_store.record_review(
            payload.position,
            analysis,
            profile_id=payload.profile_id,
        )
        return RatePlayedMoveRecordedResponse(review_id=review_id, analysis=analysis)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/training/summary", response_model=TrainingSummaryResponse)
def training_summary_endpoint(profile_id: str = "default") -> TrainingSummaryResponse:
    summary = training_store.summary(profile_id=profile_id)
    return TrainingSummaryResponse(
        total_moves=summary.total_moves,
        average_equity_loss=summary.average_equity_loss,
        inaccuracies=summary.inaccuracies,
        mistakes=summary.mistakes,
        blunders=summary.blunders,
        last_recorded_at=summary.last_recorded_at,
    )


@app.get("/training/mistakes", response_model=TrainingMistakesResponse)
def training_mistakes_endpoint(limit: int = 20, profile_id: str = "default") -> TrainingMistakesResponse:
    return TrainingMistakesResponse(mistakes=training_store.top_mistakes(limit=limit, profile_id=profile_id))


@app.get("/training/leaks", response_model=TrainingLeaksResponse)
def training_leaks_endpoint(profile_id: str = "default") -> TrainingLeaksResponse:
    return TrainingLeaksResponse(leaks=training_store.leak_summary(profile_id=profile_id))


@app.get("/training/drills", response_model=TrainingDrillsResponse)
def training_drills_endpoint(
    limit: int = 10,
    leak_category: str | None = None,
    profile_id: str = "default",
) -> TrainingDrillsResponse:
    drills = training_store.drill_candidates(
        limit=limit,
        leak_category=leak_category,
        profile_id=profile_id,
    )
    return TrainingDrillsResponse(drills=drills)


@app.post("/training/drills/attempt", response_model=TrainingDrillAttemptResponse)
def training_drill_attempt_endpoint(
    payload: TrainingDrillAttemptRequest,
) -> TrainingDrillAttemptResponse:
    try:
        result = training_store.record_drill_attempt(
            review_id=payload.review_id,
            chosen_notation=payload.chosen_notation,
            profile_id=payload.profile_id,
        )
        return TrainingDrillAttemptResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/training/drills/summary", response_model=TrainingDrillSummaryResponse)
def training_drill_summary_endpoint(profile_id: str = "default") -> TrainingDrillSummaryResponse:
    return TrainingDrillSummaryResponse.model_validate(training_store.drill_summary(profile_id=profile_id))


@app.get("/training/dashboard", response_model=TrainingDashboardResponse)
def training_dashboard_endpoint(profile_id: str = "default") -> TrainingDashboardResponse:
    raw_summary = training_store.summary(profile_id=profile_id)
    summary = TrainingSummaryResponse(
        total_moves=raw_summary.total_moves,
        average_equity_loss=raw_summary.average_equity_loss,
        inaccuracies=raw_summary.inaccuracies,
        mistakes=raw_summary.mistakes,
        blunders=raw_summary.blunders,
        last_recorded_at=raw_summary.last_recorded_at,
    )
    leaks = TrainingLeaksResponse(leaks=training_store.leak_summary(profile_id=profile_id))
    drill_summary = TrainingDrillSummaryResponse.model_validate(
        training_store.drill_summary(profile_id=profile_id)
    )
    jobs = AnalysisJobListResponse(
        jobs=[
            _job_to_response(job)
            for job in analysis_store.list_jobs(profile_id=profile_id, status=None, limit=10)
        ]
    )
    return TrainingDashboardResponse(
        summary=summary,
        leaks=leaks,
        drill_summary=drill_summary,
        recent_jobs=jobs,
    )


@app.post("/cube/decision", response_model=CubeDecisionResponse)
def cube_decision_endpoint(payload: CubeDecisionRequest) -> CubeDecisionResponse:
    return evaluate_cube_decision(payload)


@app.post("/analyze-position", response_model=AnalyzePositionResponse)
def analyze_position_endpoint(payload: AnalyzePositionRequest) -> AnalyzePositionResponse:
    try:
        analyzed = _analyze_position(payload)
        legal_moves = generate_legal_moves(payload.position)
        return AnalyzePositionResponse(
            best_move=analyzed.best_move,
            top_moves=analyzed.top_moves,
            legal_move_count=len(legal_moves),
        )
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/play-turn", response_model=SessionPlayTurnResponse)
def play_session_turn_endpoint(
    session_id: int,
    payload: SessionPlayTurnRequest,
) -> SessionPlayTurnResponse:
    state = session_store.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    if str(state["status"]) != "active":
        raise HTTPException(status_code=400, detail=f"session {session_id} is not active")

    current_position = state["current_position"]

    try:
        next_dice = payload.next_dice or (random.randint(1, 6), random.randint(1, 6))
        analysis = _rate_played_move(
            RatePlayedMoveRequest(position=current_position, played_move=payload.played_move)
        )
        if payload.record_training:
            training_store.record_review(
                current_position,
                analysis,
                profile_id=str(state["profile_id"]),
            )

        next_position = apply_move_to_position(
            position=current_position,
            move=payload.played_move,
            next_dice=next_dice,
        )
        advanced = session_store.apply_turn(
            session_id=session_id,
            previous_position=current_position,
            new_position=next_position,
            analysis=analysis,
        )
        return SessionPlayTurnResponse(
            session_id=int(advanced["session_id"]),
            move_count=int(advanced["move_count"]),
            analysis=analysis,
            current_position=advanced["current_position"],
        )
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/ai-turn", response_model=SessionAIMoveResponse)
def play_session_ai_turn_endpoint(
    session_id: int,
    payload: SessionAIMoveRequest,
) -> SessionAIMoveResponse:
    state = session_store.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    if str(state["status"]) != "active":
        raise HTTPException(status_code=400, detail=f"session {session_id} is not active")

    current_position = state["current_position"]

    try:
        next_dice = payload.next_dice or (random.randint(1, 6), random.randint(1, 6))
        legal_moves = generate_legal_moves(current_position)
        if not legal_moves:
            raise HTTPException(status_code=400, detail="no legal moves available")

        analyzed = runtime.analyze_move(
            AnalyzeMoveRequest(
                position=current_position,
                played_move=legal_moves[0],
                candidate_moves=legal_moves,
            )
        )
        selected = next((move for move in legal_moves if move.notation == analyzed.best_move.notation), None)
        if selected is None:
            raise HTTPException(status_code=500, detail="best move not found in legal move list")

        if not payload.apply_move:
            return SessionAIMoveResponse(
                session_id=session_id,
                selected_move=analyzed.best_move,
                top_moves=analyzed.top_moves,
                move_count=int(state["move_count"]),
                current_position=None,
            )

        applied_analysis = runtime.analyze_move(
            AnalyzeMoveRequest(
                position=current_position,
                played_move=selected,
                candidate_moves=legal_moves,
            )
        )
        next_position = apply_move_to_position(
            position=current_position,
            move=selected,
            next_dice=next_dice,
        )
        advanced = session_store.apply_turn(
            session_id=session_id,
            previous_position=current_position,
            new_position=next_position,
            analysis=applied_analysis,
        )
        return SessionAIMoveResponse(
            session_id=session_id,
            selected_move=analyzed.best_move,
            top_moves=analyzed.top_moves,
            move_count=int(advanced["move_count"]),
            current_position=advanced["current_position"],
        )
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate_candidate_moves(position, candidate_moves) -> None:
    legal_signatures = legal_move_signatures(position)
    if not legal_signatures:
        raise HTTPException(status_code=400, detail="no legal moves available")
    for move in candidate_moves:
        if move_signature(move) not in legal_signatures:
            raise HTTPException(
                status_code=400,
                detail=f"candidate move is not legal for this position/dice: {move.notation}",
            )
