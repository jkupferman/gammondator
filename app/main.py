import os

from fastapi import FastAPI, HTTPException

from app.analysis import apply_move_to_position
from app.backends import BackendUnavailableError, load_backend
from app.movegen import generate_legal_moves
from app.session_store import SessionStore
from app.schemas import (
    AnalyzePositionRequest,
    AnalyzePositionResponse,
    AnalyzeMoveRequest,
    AnalyzeMoveResponse,
    AnalyzerInfoResponse,
    ChooseAIMoveRequest,
    ChooseAIMoveFromPositionRequest,
    ChooseAIMoveResponse,
    LegalMovesRequest,
    LegalMovesResponse,
    RatePlayedMoveRequest,
    RatePlayedMoveRecordedResponse,
    SessionCreateRequest,
    SessionAIMoveRequest,
    SessionAIMoveResponse,
    SessionPlayTurnRequest,
    SessionPlayTurnResponse,
    SessionStateResponse,
    TrainingMistakesResponse,
    TrainingLeaksResponse,
    TrainingSummaryResponse,
)
from app.training_store import TrainingStore

app = FastAPI(title="Gammondator API", version="0.1.0")
runtime = load_backend()
training_store = TrainingStore(db_path=os.getenv("GAMMONDATOR_DB_PATH", "gammondator.db"))
session_store = SessionStore(db_path=os.getenv("GAMMONDATOR_DB_PATH", "gammondator.db"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "backend": runtime.backend.name}


@app.get("/analyzer", response_model=AnalyzerInfoResponse)
def analyzer_info() -> AnalyzerInfoResponse:
    return AnalyzerInfoResponse(
        backend=runtime.backend.name,
        fallback_active=runtime.fallback_active,
        details=runtime.details,
    )


@app.post("/sessions", response_model=SessionStateResponse)
def create_session_endpoint(payload: SessionCreateRequest) -> SessionStateResponse:
    created = session_store.create_session(payload.initial_position)
    return SessionStateResponse(
        session_id=int(created["session_id"]),
        status=str(created["status"]),
        move_count=int(created["move_count"]),
        current_position=created["current_position"],
    )


@app.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session_endpoint(session_id: int) -> SessionStateResponse:
    state = session_store.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    return SessionStateResponse(
        session_id=int(state["session_id"]),
        status=str(state["status"]),
        move_count=int(state["move_count"]),
        current_position=state["current_position"],
    )


@app.post("/analyze-move", response_model=AnalyzeMoveResponse)
def analyze_move_endpoint(payload: AnalyzeMoveRequest) -> AnalyzeMoveResponse:
    try:
        return runtime.backend.analyze_move(payload)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/choose-ai-move", response_model=ChooseAIMoveResponse)
def choose_ai_move_endpoint(payload: ChooseAIMoveRequest) -> ChooseAIMoveResponse:
    try:
        analyzed = runtime.backend.analyze_move(
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

    legal_keys = {tuple((s.from_point, s.to_point) for s in m.steps) for m in legal_moves}
    played_key = tuple((s.from_point, s.to_point) for s in payload.played_move.steps)
    if played_key not in legal_keys:
        raise HTTPException(status_code=400, detail="played_move is not legal for this position/dice")

    return runtime.backend.analyze_move(
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

    return runtime.backend.analyze_move(
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
        review_id = training_store.record_review(payload.position, analysis)
        return RatePlayedMoveRecordedResponse(review_id=review_id, analysis=analysis)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/training/summary", response_model=TrainingSummaryResponse)
def training_summary_endpoint() -> TrainingSummaryResponse:
    summary = training_store.summary()
    return TrainingSummaryResponse(
        total_moves=summary.total_moves,
        average_equity_loss=summary.average_equity_loss,
        inaccuracies=summary.inaccuracies,
        mistakes=summary.mistakes,
        blunders=summary.blunders,
        last_recorded_at=summary.last_recorded_at,
    )


@app.get("/training/mistakes", response_model=TrainingMistakesResponse)
def training_mistakes_endpoint(limit: int = 20) -> TrainingMistakesResponse:
    return TrainingMistakesResponse(mistakes=training_store.top_mistakes(limit=limit))


@app.get("/training/leaks", response_model=TrainingLeaksResponse)
def training_leaks_endpoint() -> TrainingLeaksResponse:
    return TrainingLeaksResponse(leaks=training_store.leak_summary())


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

    current_position = state["current_position"]

    try:
        analysis = _rate_played_move(
            RatePlayedMoveRequest(position=current_position, played_move=payload.played_move)
        )
        if payload.record_training:
            training_store.record_review(current_position, analysis)

        next_position = apply_move_to_position(
            position=current_position,
            move=payload.played_move,
            next_dice=payload.next_dice,
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

    current_position = state["current_position"]

    try:
        legal_moves = generate_legal_moves(current_position)
        if not legal_moves:
            raise HTTPException(status_code=400, detail="no legal moves available")

        analyzed = runtime.backend.analyze_move(
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

        applied_analysis = runtime.backend.analyze_move(
            AnalyzeMoveRequest(
                position=current_position,
                played_move=selected,
                candidate_moves=legal_moves,
            )
        )
        next_position = apply_move_to_position(
            position=current_position,
            move=selected,
            next_dice=payload.next_dice,
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
