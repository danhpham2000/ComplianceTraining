import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, UUIDTimestampMixin


class Organization(UUIDTimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ai_script_profile_name: Mapped[str | None] = mapped_column(String(255))
    ai_script_markdown: Mapped[str | None] = mapped_column(Text)


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    time_zone: Mapped[str | None] = mapped_column(String(80))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_code_hash: Mapped[str | None] = mapped_column(String(255))
    verification_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(UUIDTimestampMixin, Base):
    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link_url: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    user: Mapped["User"] = relationship()


class AuthSession(UUIDTimestampMixin, Base):
    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship()


class OrganizationMember(UUIDTimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped["Organization"] = relationship()
    user: Mapped["User"] = relationship()


class Team(UUIDTimestampMixin, Base):
    __tablename__ = "teams"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class TeamMember(Base):
    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrainingCourse(UUIDTimestampMixin, Base):
    __tablename__ = "training_courses"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    versions: Mapped[list["TrainingVersion"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="TrainingVersion.version_number",
    )


class TrainingVersion(UUIDTimestampMixin, Base):
    __tablename__ = "training_versions"
    __table_args__ = (UniqueConstraint("course_id", "version_number"),)

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_courses.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped["TrainingCourse"] = relationship(back_populates="versions")
    content_sources: Mapped[list["ContentSource"]] = relationship(
        back_populates="training_version",
        cascade="all, delete-orphan",
    )
    learning_objectives: Mapped[list["LearningObjective"]] = relationship(
        back_populates="training_version",
        cascade="all, delete-orphan",
        order_by="LearningObjective.sort_order",
    )
    questions: Mapped[list["Question"]] = relationship(
        back_populates="training_version",
        cascade="all, delete-orphan",
        order_by="Question.sort_order",
    )


class ContentSource(UUIDTimestampMixin, Base):
    __tablename__ = "content_sources"

    training_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_versions.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)

    training_version: Mapped["TrainingVersion"] = relationship(back_populates="content_sources")
    transcripts: Mapped[list["Transcript"]] = relationship(
        back_populates="content_source",
        cascade="all, delete-orphan",
    )


class Transcript(UUIDTimestampMixin, Base):
    __tablename__ = "transcripts"

    content_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("content_sources.id"), nullable=False)
    language: Mapped[str | None] = mapped_column(String(12))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    segments_json: Mapped[list[dict] | None] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(50))

    content_source: Mapped["ContentSource"] = relationship(back_populates="transcripts")


class LearningObjective(UUIDTimestampMixin, Base):
    __tablename__ = "learning_objectives"

    training_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_versions.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    training_version: Mapped["TrainingVersion"] = relationship(back_populates="learning_objectives")


class Question(UUIDTimestampMixin, Base):
    __tablename__ = "questions"

    training_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_versions.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(255))
    difficulty: Mapped[str | None] = mapped_column(String(50))
    hint: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    source_start_seconds: Mapped[int | None] = mapped_column(Integer)
    source_end_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    training_version: Mapped["TrainingVersion"] = relationship(back_populates="questions")
    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.sort_order",
    )


class QuestionOption(UUIDTimestampMixin, Base):
    __tablename__ = "question_options"

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped["Question"] = relationship(back_populates="options")


class Assignment(UUIDTimestampMixin, Base):
    __tablename__ = "assignments"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    training_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_versions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    passing_score: Mapped[float] = mapped_column(Float, nullable=False, default=80)
    required_watch_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=90)
    max_attempts_per_question: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    allow_retakes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    recipients: Mapped[list["AssignmentRecipient"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
    )


class AssignmentRecipient(UUIDTimestampMixin, Base):
    __tablename__ = "assignment_recipients"
    __table_args__ = (UniqueConstraint("assignment_id", "user_id"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="NOT_STARTED")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_score: Mapped[float | None] = mapped_column(Float)
    first_attempt_accuracy: Mapped[float | None] = mapped_column(Float)
    final_accuracy: Mapped[float | None] = mapped_column(Float)

    assignment: Mapped["Assignment"] = relationship(back_populates="recipients")
    user: Mapped["User"] = relationship()


class TrainingSession(UUIDTimestampMixin, Base):
    __tablename__ = "training_sessions"

    assignment_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignment_recipients.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    quiz_sessions: Mapped[list["QuizSession"]] = relationship(
        back_populates="training_session",
        cascade="all, delete-orphan",
    )
    video_progress_records: Mapped[list["VideoProgress"]] = relationship(
        back_populates="training_session",
        cascade="all, delete-orphan",
    )


class VideoProgress(UUIDTimestampMixin, Base):
    __tablename__ = "video_progress"
    __table_args__ = (UniqueConstraint("training_session_id", "content_source_id"),)

    training_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_sessions.id"), nullable=False)
    content_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("content_sources.id"), nullable=False)
    furthest_position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_watched_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watch_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    last_position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    training_session: Mapped["TrainingSession"] = relationship(back_populates="video_progress_records")
    intervals: Mapped[list["VideoWatchInterval"]] = relationship(
        back_populates="video_progress",
        cascade="all, delete-orphan",
    )


class VideoWatchInterval(UUIDTimestampMixin, Base):
    __tablename__ = "video_watch_intervals"

    video_progress_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("video_progress.id"), nullable=False)
    start_second: Mapped[int] = mapped_column(Integer, nullable=False)
    end_second: Mapped[int] = mapped_column(Integer, nullable=False)

    video_progress: Mapped["VideoProgress"] = relationship(back_populates="intervals")


class QuizSession(UUIDTimestampMixin, Base):
    __tablename__ = "quiz_sessions"

    training_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_sessions.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    first_attempt_accuracy: Mapped[float | None] = mapped_column(Float)
    final_accuracy: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="IN_PROGRESS")

    training_session: Mapped["TrainingSession"] = relationship(back_populates="quiz_sessions")
    attempts: Mapped[list["QuestionAttempt"]] = relationship(
        back_populates="quiz_session",
        cascade="all, delete-orphan",
    )
    summaries: Mapped[list["TrainingSummary"]] = relationship(
        back_populates="quiz_session",
        cascade="all, delete-orphan",
    )


class QuestionAttempt(UUIDTimestampMixin, Base):
    __tablename__ = "question_attempts"
    __table_args__ = (
        UniqueConstraint("quiz_session_id", "question_id", "attempt_number"),
        UniqueConstraint("quiz_session_id", "client_request_key"),
    )

    quiz_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_sessions.id"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), nullable=False)
    question_option_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("question_options.id"))
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    client_request_key: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    quiz_session: Mapped["QuizSession"] = relationship(back_populates="attempts")


class TrainingSummary(UUIDTimestampMixin, Base):
    __tablename__ = "training_summaries"

    quiz_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quiz_sessions.id"), nullable=False)
    strengths_json: Mapped[list[str] | None] = mapped_column(JSON)
    needs_improvement_json: Mapped[list[str] | None] = mapped_column(JSON)
    recommended_review_json: Mapped[list[dict] | None] = mapped_column(JSON)
    summary_text: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    quiz_session: Mapped["QuizSession"] = relationship(back_populates="summaries")


class AuditLog(UUIDTimestampMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
