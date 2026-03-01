from fastapi import FastAPI, HTTPException

from app.backends import BackendUnavailableError, load_backend
from app.schemas import (
    AnalyzeMoveRequest,
    AnalyzeMoveResponse,
    AnalyzerInfoResponse,
    ChooseAIMoveRequest,
    ChooseAIMoveResponse,
)

app = FastAPI(title="Gammondator API", version="0.1.0")
runtime = load_backend()


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
