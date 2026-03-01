import os

from fastapi import FastAPI, HTTPException

from app.backends import BackendUnavailableError, load_backend
from app.movegen import generate_legal_moves
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
    TrainingMistakesResponse,
    TrainingSummaryResponse,
)
from app.training_store import TrainingStore

app = FastAPI(title="Gammondator API", version="0.1.0")
runtime = load_backend()
training_store = TrainingStore(db_path=os.getenv("GAMMONDATOR_DB_PATH", "gammondator.db"))


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
