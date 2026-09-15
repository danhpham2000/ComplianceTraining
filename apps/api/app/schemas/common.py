import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIMessage(BaseModel):
    message: str


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class ActorSummary(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None = None
    role: str
    time_zone: str | None = None
    organization: OrganizationSummary


class DirectoryUserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None = None
    time_zone: str | None = None
    role: str
    status: str = "ACTIVE"


class OptionAdminOut(BaseModel):
    id: uuid.UUID
    text: str
    is_correct: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class OptionEmployeeOut(BaseModel):
    id: uuid.UUID
    text: str
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class QuestionAdminOut(BaseModel):
    id: uuid.UUID
    text: str
    type: str
    topic: str | None = None
    difficulty: str | None = None
    hint: str | None = None
    explanation: str | None = None
    source_start_seconds: int | None = None
    source_end_seconds: int | None = None
    status: str
    sort_order: int
    options: list[OptionAdminOut]

    model_config = ConfigDict(from_attributes=True)


class QuestionEmployeeOut(BaseModel):
    id: uuid.UUID
    text: str
    type: str
    topic: str | None = None
    hint: str | None = None
    sort_order: int
    options: list[OptionEmployeeOut]
    attempts_used: int = 0
    attempts_remaining: int = 0
    terminal: bool = False


class LearningObjectiveOut(BaseModel):
    id: uuid.UUID
    text: str
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ContentSourceOut(BaseModel):
    id: uuid.UUID
    source_type: str
    source_url: str | None = None
    external_id: str | None = None
    title: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ResearchMaterialSourceOut(BaseModel):
    title: str
    url: str
    domain: str | None = None


class ResearchMaterialSectionOut(BaseModel):
    title: str
    summary: str
    bullets: list[str] = []
    citations: list[str] = []


class ResearchMaterialOut(BaseModel):
    query: str | None = None
    overview: str | None = None
    sections: list[ResearchMaterialSectionOut] = []
    sources: list[ResearchMaterialSourceOut] = []


class CourseSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    category: str | None = None
    status: str
    current_version_id: uuid.UUID | None = None
    version_number: int | None = None
    question_count: int = 0
    published_at: datetime | None = None
    content_source: ContentSourceOut | None = None


class AssignmentSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str | None = None
    training_title: str
    due_at: datetime | None = None
    start_at: datetime | None = None
    passing_score: float
    required_watch_percentage: float
    max_attempts_per_question: int
    watch_percentage: float = 0
    final_score: float | None = None
    question_count: int = 0
    completed_at: datetime | None = None
    certificate: "CertificateOut | None" = None


class CertificateOut(BaseModel):
    certificate_number: str
    issued_at: datetime
    employee_name: str
    employee_email: str
    training_title: str
    assignment_name: str
    score: float | None = None
    download_path: str


class OverviewMetricsOut(BaseModel):
    total_assigned: int = 0
    not_started: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0
    overdue: int = 0
    completion_rate: float = 0
    average_score: float = 0
    average_first_attempt_accuracy: float = 0
    average_final_accuracy: float = 0


class TopicMetricOut(BaseModel):
    topic: str = Field(default="Uncategorized")
    questions_answered: int = 0
    first_attempt_accuracy: float = 0
    final_accuracy: float = 0
    failure_rate: float = 0


class LearnerProgressOut(BaseModel):
    assignment_recipient_id: uuid.UUID
    assignment_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_email: str
    assignment_name: str
    training_title: str
    status: str
    due_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    final_score: float | None = None
    certificate: CertificateOut | None = None
