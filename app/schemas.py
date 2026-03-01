from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Side = Literal["white", "black"]


class MoveStep(BaseModel):
    from_point: int = Field(ge=0, le=25)
    to_point: int = Field(ge=0, le=25)


class Move(BaseModel):
    notation: str
    steps: list[MoveStep] = Field(min_length=1)


class Position(BaseModel):
    """
    points uses 24 slots (index 0 => point 1, index 23 => point 24).
    Positive values = white checkers, negative values = black checkers.
    """

    points: list[int] = Field(min_length=24, max_length=24)
    bar_white: int = Field(ge=0, le=15)
    bar_black: int = Field(ge=0, le=15)
    off_white: int = Field(ge=0, le=15)
    off_black: int = Field(ge=0, le=15)
    turn: Side
    cube_value: int = Field(default=1, ge=1)
    dice: tuple[int, int] = Field(description="Dice that generated this move decision")

    @field_validator("dice")
    @classmethod
    def validate_dice(cls, value: tuple[int, int]) -> tuple[int, int]:
        d1, d2 = value
        if not (1 <= d1 <= 6 and 1 <= d2 <= 6):
            raise ValueError("dice must be between 1 and 6")
        return value

    @model_validator(mode="after")
    def validate_total_checkers(self) -> "Position":
        white_on_board = sum(x for x in self.points if x > 0)
        black_on_board = -sum(x for x in self.points if x < 0)

        white_total = white_on_board + self.bar_white + self.off_white
        black_total = black_on_board + self.bar_black + self.off_black

        if white_total != 15:
            raise ValueError(f"white checker count must be 15, got {white_total}")
        if black_total != 15:
            raise ValueError(f"black checker count must be 15, got {black_total}")

        return self


class AnalyzeMoveRequest(BaseModel):
    position: Position
    played_move: Move
    candidate_moves: list[Move] = Field(min_length=1)


class MoveScore(BaseModel):
    notation: str
    equity: float
    delta_vs_best: float
    quality: Literal["excellent", "good", "inaccuracy", "mistake", "blunder"]
    why: list[str]


class AnalyzeMoveResponse(BaseModel):
    best_move: MoveScore
    played_move: MoveScore
    top_moves: list[MoveScore]


class ChooseAIMoveRequest(BaseModel):
    position: Position
    candidate_moves: list[Move] = Field(min_length=1)


class ChooseAIMoveResponse(BaseModel):
    selected_move: MoveScore
    top_moves: list[MoveScore]


class AnalyzerInfoResponse(BaseModel):
    backend: str
    fallback_active: bool
    details: str


class LegalMovesRequest(BaseModel):
    position: Position


class LegalMovesResponse(BaseModel):
    moves: list[Move]


class ChooseAIMoveFromPositionRequest(BaseModel):
    position: Position


class RatePlayedMoveRequest(BaseModel):
    position: Position
    played_move: Move


class RatePlayedMoveRecordedResponse(BaseModel):
    review_id: int
    analysis: AnalyzeMoveResponse


class TrainingSummaryResponse(BaseModel):
    total_moves: int
    average_equity_loss: float
    inaccuracies: int
    mistakes: int
    blunders: int
    last_recorded_at: str | None


class TrainingMistakesResponse(BaseModel):
    mistakes: list[dict[str, object]]


class AnalyzePositionRequest(BaseModel):
    position: Position


class AnalyzePositionResponse(BaseModel):
    best_move: MoveScore
    top_moves: list[MoveScore]
    legal_move_count: int


class TrainingLeakItem(BaseModel):
    leak_category: str
    move_count: int
    average_equity_loss: float
    max_equity_loss: float


class TrainingLeaksResponse(BaseModel):
    leaks: list[TrainingLeakItem]
