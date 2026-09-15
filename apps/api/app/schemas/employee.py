import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import AssignmentSummaryOut, CertificateOut, QuestionEmployeeOut


class VideoProgressIn(BaseModel):
    start_second: int = Field(ge=0)
    end_second: int = Field(ge=0)
    current_position_seconds: int = Field(ge=0)
    duration_seconds: int | None = Field(default=None, ge=1)


class VideoProgressOut(BaseModel):
    unique_watched_seconds: int
    furthest_position_seconds: int
    watch_percentage: float


class QuizStartOut(BaseModel):
    quiz_session_id: uuid.UUID
    assignment_id: uuid.UUID
    max_attempts_per_question: int
    questions: list[QuestionEmployeeOut]


class QuestionAttemptIn(BaseModel):
    option_id: uuid.UUID
    idempotency_key: str


class QuestionAttemptResultOut(BaseModel):
    correct: bool
    attempt_number: int
    attempts_remaining: int
    terminal: bool
    message: str | None = None
    hint: str | None = None
    explanation: str | None = None
    correct_option_id: uuid.UUID | None = None


class AssignmentDetailOut(AssignmentSummaryOut):
    assignment_recipient_id: uuid.UUID
    description: str | None = None
    video_url: str | None = None
    video_title: str | None = None
    video_duration_seconds: int | None = None
    quiz_ready: bool = False


class TrainingSummaryOut(BaseModel):
    strengths: list[str] = []
    needs_improvement: list[str] = []
    recommended_review: list[dict] = []
    summary: str | None = None


class ResultOut(BaseModel):
    status: str
    completed_at: datetime | None = None
    official_score: float | None = None
    passing_score: float
    first_attempt_accuracy: float | None = None
    final_accuracy: float | None = None
    video_completion_percentage: float
    summary: TrainingSummaryOut | None = None
    question_breakdown: list[QuestionEmployeeOut]
    certificate: CertificateOut | None = None
