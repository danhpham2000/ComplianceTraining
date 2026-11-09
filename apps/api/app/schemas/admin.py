import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import CourseSummaryOut, LearningObjectiveOut, QuestionAdminOut, ResearchMaterialOut


class TrainingCreateIn(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None


class GenerateAssessmentIn(BaseModel):
    question_count: int = Field(default=6, ge=3, le=12)
    admin_instructions: str | None = None


class ResearchTrainingBuildIn(BaseModel):
    research_query: str = Field(min_length=6)
    question_count: int = Field(default=6, ge=3, le=12)


class PublishTrainingIn(BaseModel):
    recipient_user_ids: list[uuid.UUID] = Field(default_factory=list)
    assign_to_all: bool = True


class TrainingDetailOut(CourseSummaryOut):
    learning_objectives: list[LearningObjectiveOut] = []
    questions: list[QuestionAdminOut] = []
    research_material: ResearchMaterialOut | None = None


class UpdateQuestionOptionIn(BaseModel):
    id: uuid.UUID
    text: str = Field(min_length=1, max_length=1000)
    is_correct: bool


class UpdateQuestionIn(BaseModel):
    text: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    hint: str | None = None
    explanation: str | None = None
    status: str | None = None
    options: list[UpdateQuestionOptionIn] | None = Field(default=None, min_length=2, max_length=6)

    @model_validator(mode="after")
    def validate_correct_option(self):
        if self.options is not None and sum(option.is_correct for option in self.options) != 1:
            raise ValueError("Exactly one answer option must be marked correct.")
        return self


class AssignmentCreateIn(BaseModel):
    training_version_id: uuid.UUID
    name: str
    recipient_user_ids: list[uuid.UUID] = Field(default_factory=list)
    assign_to_all: bool = False
    start_at: datetime | None = None
    due_at: datetime | None = None
    passing_score: float = Field(default=80, ge=0, le=100)
    required_watch_percentage: float = Field(default=90, ge=0, le=100)
    max_attempts_per_question: int = Field(default=2, ge=1, le=5)
    allow_retakes: bool = False


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    link_url: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime
    metadata_json: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationReadIn(BaseModel):
    notification_ids: list[uuid.UUID] = Field(default_factory=list)
    mark_all: bool = False


class AssignmentAdminDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    training_version_id: uuid.UUID
    training_title: str
    start_at: datetime | None = None
    due_at: datetime | None = None
    passing_score: float
    required_watch_percentage: float
    max_attempts_per_question: int
    allow_retakes: bool
    recipients: list[dict]

    model_config = ConfigDict(from_attributes=True)
