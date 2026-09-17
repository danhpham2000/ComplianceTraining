from datetime import datetime, timezone
import threading
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.client import generate_assessment
from app.api.deps import CurrentActor, DBSession
from app.db.session import SessionLocal
from app.models import (
    Assignment,
    AssignmentRecipient,
    ContentSource,
    LearningObjective,
    Notification,
    Organization,
    OrganizationMember,
    Question,
    QuestionOption,
    TrainingCourse,
    TrainingSession,
    TrainingVersion,
    Transcript,
    User,
    VideoProgress,
    QuizSession,
)
from app.schemas.admin import (
    GenerateAssessmentIn,
    PublishTrainingIn,
    ResearchTrainingBuildIn,
    TrainingCreateIn,
    TrainingDetailOut,
    UpdateQuestionIn,
)
from app.schemas.common import (
    APIMessage,
    CourseSummaryOut,
    QuestionAdminOut,
    ResearchMaterialOut,
    ResearchMaterialSectionOut,
    ResearchMaterialSourceOut,
)
from app.services.audit import log_audit
from app.services.auth import require_roles
from app.services.notifications import (
    notify_assignment_recipients,
    notify_training_build_completed,
    notify_training_build_failed,
)
from app.services.generated_assets import persist_generated_training_assets
from app.services.research_training import build_research_training, rebuild_lecture_video_from_segments, remove_generated_training_assets


router = APIRouter(tags=["training"])


def _load_training_for_build(db, *, training_id, organization_id) -> TrainingCourse | None:
    return db.execute(
        select(TrainingCourse)
        .where(TrainingCourse.id == training_id, TrainingCourse.organization_id == organization_id)
        .options(
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.questions).selectinload(Question.options),
            selectinload(TrainingCourse.versions)
            .selectinload(TrainingVersion.content_sources)
            .selectinload(ContentSource.transcripts),
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.learning_objectives),
        )
    ).scalar_one_or_none()


def _run_research_training_build(
    *,
    training_id,
    organization_id,
    actor_user_id,
    research_query: str,
    generation_mode: str,
    question_count: int,
) -> None:
    db = SessionLocal()
    try:
        course = _load_training_for_build(db, training_id=training_id, organization_id=organization_id)
        organization = db.execute(select(Organization).where(Organization.id == organization_id)).scalar_one_or_none()
        if not course or not organization:
            return

        generated = build_research_training(
            training_id=str(training_id),
            title=course.title,
            research_query=research_query,
            generation_mode=generation_mode,
            question_count=question_count,
            script_profile_name=organization.ai_script_profile_name,
            script_markdown=organization.ai_script_markdown,
        )

        db.expire_all()
        course = _load_training_for_build(db, training_id=training_id, organization_id=organization_id)
        if not course:
            remove_generated_training_assets(f"/generated/trainings/{training_id}/lesson.mp4")
            return

        version = course.versions[-1]
        course.description = generated.description
        course.status = "READY"
        version.status = "READY"
        source = ContentSource(
            source_type="GENERATED_VIDEO",
            source_url=generated.video_url,
            external_id=research_query,
            title=generated.source_title,
            duration_seconds=generated.duration_seconds,
            thumbnail_url=generated.thumbnail_url,
        )
        source.transcripts.append(
            Transcript(
                language="en",
                text=generated.transcript_text,
                segments_json=generated.transcript_segments,
                source="RESEARCH_GENERATED",
            )
        )
        version.content_sources.append(source)
        persist_generated_training_assets(db, training_id=course.id)

        for index, objective in enumerate(generated.learning_objectives, start=1):
            version.learning_objectives.append(LearningObjective(text=objective, sort_order=index))

        for q_index, generated_question in enumerate(generated.questions, start=1):
            question = Question(
                type=generated_question.type,
                text=generated_question.question,
                topic=generated_question.topic,
                difficulty=generated_question.difficulty,
                hint=generated_question.hint,
                explanation=generated_question.explanation,
                source_start_seconds=generated_question.sourceStartSeconds,
                source_end_seconds=generated_question.sourceEndSeconds,
                status="DRAFT",
                sort_order=q_index,
            )
            for o_index, option in enumerate(generated_question.options, start=1):
                question.options.append(
                    QuestionOption(text=option.text, is_correct=option.isCorrect, sort_order=o_index)
                )
            version.questions.append(question)

        log_audit(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="RESEARCH_TRAINING_READY",
            entity_type="training_course",
            entity_id=course.id,
            metadata={"query": research_query, "generation_mode": generation_mode, "question_count": question_count},
        )
        notify_training_build_completed(
            db,
            organization_id=organization_id,
            training_id=course.id,
            training_title=course.title,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        remove_generated_training_assets(f"/generated/trainings/{training_id}/lesson.mp4")
        course = _load_training_for_build(db, training_id=training_id, organization_id=organization_id)
        if not course:
            return
        version = course.versions[-1]
        error_message = str(exc).strip() or "Training generation failed."
        course.status = "FAILED"
        version.status = "FAILED"
        course.description = error_message[:800]
        log_audit(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="RESEARCH_TRAINING_FAILED",
            entity_type="training_course",
            entity_id=course.id,
            metadata={"query": research_query, "generation_mode": generation_mode, "error": error_message[:240]},
        )
        notify_training_build_failed(
            db,
            organization_id=organization_id,
            training_id=course.id,
            training_title=course.title,
            error_message=error_message,
        )
        db.commit()
    finally:
        db.close()


def _launch_research_training_build(**kwargs) -> None:
    worker = threading.Thread(
        target=_run_research_training_build,
        kwargs=kwargs,
        daemon=True,
        name=f"training-build-{kwargs.get('training_id')}",
    )
    worker.start()


def _run_training_video_repair(*, training_id, organization_id) -> None:
    db = SessionLocal()
    try:
        course = _load_training_for_build(db, training_id=training_id, organization_id=organization_id)
        if not course or not course.versions:
            return
        version = course.versions[-1]
        source = version.content_sources[0] if version.content_sources else None
        transcript = source.transcripts[0] if source and source.transcripts else None
        if not source or not transcript or not transcript.segments_json:
            return

        duration_seconds = rebuild_lecture_video_from_segments(
            training_id=str(course.id),
            title=course.title,
            segments=transcript.segments_json,
        )
        source.source_url = f"/generated/trainings/{course.id}/lesson.mp4"
        source.thumbnail_url = f"/generated/trainings/{course.id}/thumbnail.png"
        source.duration_seconds = duration_seconds
        persist_generated_training_assets(db, training_id=course.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _launch_training_video_repair(**kwargs) -> None:
    worker = threading.Thread(
        target=_run_training_video_repair,
        kwargs=kwargs,
        daemon=True,
        name=f"training-video-repair-{kwargs.get('training_id')}",
    )
    worker.start()


def derive_training_title(research_query: str) -> str:
    cleaned = " ".join(research_query.strip().rstrip(".?!").split())
    if not cleaned:
        return "Research-generated training"
    if len(cleaned) <= 88:
        return cleaned[0].upper() + cleaned[1:]
    shortened = cleaned[:85].rsplit(" ", 1)[0].strip()
    return f"{shortened}..."


def normalize_generation_mode(mode: str | None) -> str:
    normalized = (mode or "LECTURE").strip().upper()
    if normalized not in {"LECTURE", "CARTOON"}:
        raise HTTPException(status_code=422, detail="generation_mode must be LECTURE or CARTOON")
    return normalized


def serialize_course(course: TrainingCourse) -> CourseSummaryOut:
    version = course.versions[-1] if course.versions else None
    source = version.content_sources[0] if version and version.content_sources else None
    return CourseSummaryOut(
        id=course.id,
        title=course.title,
        description=course.description,
        category=course.category,
        status=course.status,
        current_version_id=version.id if version else None,
        version_number=version.version_number if version else None,
        question_count=len(version.questions) if version else 0,
        published_at=version.published_at if version else None,
        content_source=source,
    )


def build_research_material(version: TrainingVersion) -> ResearchMaterialOut | None:
    if not version.content_sources or not version.content_sources[0].transcripts:
        return None

    source = version.content_sources[0]
    transcript = source.transcripts[0]
    segments = transcript.segments_json or []
    if not segments:
        return None

    sections: list[ResearchMaterialSectionOut] = []
    ordered_sources: list[ResearchMaterialSourceOut] = []
    seen_urls: set[str] = set()

    for index, segment in enumerate(segments):
        citations = [
            str(item).strip()
            for item in (segment.get("citations") or [])
            if str(item).strip()
        ]
        for url in citations:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            domain = urlparse(url).netloc.replace("www.", "") or None
            ordered_sources.append(
                ResearchMaterialSourceOut(
                    title=domain or f"Source {len(ordered_sources) + 1}",
                    url=url,
                    domain=domain,
                )
            )

        sections.append(
            ResearchMaterialSectionOut(
                title=str(segment.get("title") or f"Section {index + 1}"),
                summary=str(segment.get("text") or "").strip(),
                bullets=[
                    str(item).strip()
                    for item in (segment.get("bullets") or [])
                    if str(item).strip()
                ],
                citations=citations,
            )
        )

    overview = sections[0].summary if sections else None
    if len(sections) > 1 and sections[0].title.strip().lower() == version.course.title.strip().lower():
        overview = sections[0].summary

    return ResearchMaterialOut(
        query=source.external_id,
        overview=overview,
        sections=sections[1:] if len(sections) > 1 else sections,
        sources=ordered_sources,
    )


@router.get("/training", response_model=list[CourseSummaryOut])
def list_training(db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    courses = db.execute(
        select(TrainingCourse)
        .where(TrainingCourse.organization_id == actor.organization_id)
        .options(
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.questions),
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.content_sources),
        )
        .order_by(TrainingCourse.created_at.desc())
    ).scalars().all()
    return [serialize_course(course) for course in courses]


@router.post("/training", response_model=CourseSummaryOut)
def create_training(payload: TrainingCreateIn, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    course = TrainingCourse(
        organization_id=actor.organization_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        status="DRAFT",
        created_by=actor.user.id,
    )
    version = TrainingVersion(version_number=1, status="DRAFT")
    course.versions.append(version)
    db.add(course)
    db.flush()
    log_audit(
        db,
        organization_id=actor.organization_id,
        actor_user_id=actor.user.id,
        action="TRAINING_CREATED",
        entity_type="training_course",
        entity_id=course.id,
        metadata={"title": payload.title},
    )
    db.commit()
    db.refresh(course)
    return serialize_course(course)


@router.post("/training/research-build", response_model=TrainingDetailOut, status_code=status.HTTP_202_ACCEPTED)
def build_research_training_course(
    payload: ResearchTrainingBuildIn,
    db: DBSession,
    actor: CurrentActor,
):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    title = derive_training_title(payload.research_query)
    generation_mode = normalize_generation_mode(payload.generation_mode)
    course = TrainingCourse(
        organization_id=actor.organization_id,
        title=title,
        description=None,
        category="Compliance Research",
        status="PROCESSING",
        created_by=actor.user.id,
    )
    version = TrainingVersion(version_number=1, status="PROCESSING")
    course.versions.append(version)
    db.add(course)
    db.flush()
    log_audit(
        db,
        organization_id=actor.organization_id,
        actor_user_id=actor.user.id,
        action="RESEARCH_TRAINING_QUEUED",
        entity_type="training_course",
        entity_id=course.id,
        metadata={
            "query": payload.research_query,
            "question_count": payload.question_count,
            "generation_mode": generation_mode,
        },
    )
    db.commit()
    _launch_research_training_build(
        training_id=course.id,
        organization_id=actor.organization_id,
        actor_user_id=actor.user.id,
        research_query=payload.research_query,
        generation_mode=generation_mode,
        question_count=payload.question_count,
    )
    return get_training(course.id, db, actor)


@router.get("/training/{training_id}", response_model=TrainingDetailOut)
def get_training(training_id, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    course = db.execute(
        select(TrainingCourse)
        .where(TrainingCourse.id == training_id, TrainingCourse.organization_id == actor.organization_id)
        .options(
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.questions).selectinload(Question.options),
            selectinload(TrainingCourse.versions)
            .selectinload(TrainingVersion.content_sources)
            .selectinload(ContentSource.transcripts),
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.learning_objectives),
        )
    ).scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Training not found")
    version = course.versions[-1]
    source = version.content_sources[0] if version.content_sources else None
    return TrainingDetailOut(
        **serialize_course(course).model_dump(),
        learning_objectives=version.learning_objectives,
        questions=[QuestionAdminOut.model_validate(question) for question in version.questions],
        research_material=build_research_material(version),
    )


@router.post("/training/{training_id}/repair-video", response_model=APIMessage, status_code=status.HTTP_202_ACCEPTED)
def repair_training_video(training_id, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    course = db.execute(
        select(TrainingCourse)
        .where(TrainingCourse.id == training_id, TrainingCourse.organization_id == actor.organization_id)
        .options(
            selectinload(TrainingCourse.versions)
            .selectinload(TrainingVersion.content_sources)
            .selectinload(ContentSource.transcripts),
        )
    ).scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Training not found")
    version = course.versions[-1] if course.versions else None
    source = version.content_sources[0] if version and version.content_sources else None
    transcript = source.transcripts[0] if source and source.transcripts else None
    if not transcript or not transcript.segments_json:
        raise HTTPException(status_code=400, detail="No transcript is available to rebuild this video.")

    _launch_training_video_repair(training_id=course.id, organization_id=actor.organization_id)
    return APIMessage(message="Video rebuild started. Refresh this page in a few minutes.")

@router.post("/training/{training_id}/generate", response_model=TrainingDetailOut)
def run_generation(training_id, payload: GenerateAssessmentIn, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    course = db.execute(
        select(TrainingCourse)
        .where(TrainingCourse.id == training_id, TrainingCourse.organization_id == actor.organization_id)
        .options(
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.content_sources).selectinload(ContentSource.transcripts),
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.questions).selectinload(Question.options),
            selectinload(TrainingCourse.versions).selectinload(TrainingVersion.learning_objectives),
        )
    ).scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Training not found")
    version = course.versions[-1]
    if not version.content_sources or not version.content_sources[0].transcripts:
        raise HTTPException(status_code=400, detail="Attach a video and transcript before generation")

    transcript = version.content_sources[0].transcripts[0]
    if transcript.source == "FALLBACK":
        raise HTTPException(
            status_code=400,
            detail=(
                "This training source does not expose usable transcript content. "
                "Rebuild the training source before generating questions."
            ),
        )
    version.status = "PROCESSING"
    course.status = "PROCESSING"
    db.flush()

    try:
        assessment = generate_assessment(
            title=course.title,
            transcript_text=transcript.text,
            transcript_segments=transcript.segments_json or [],
            admin_instructions=payload.admin_instructions,
            question_count=payload.question_count,
        )
    except Exception as exc:
        version.status = "DRAFT"
        course.status = "DRAFT"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Assessment generation failed. {exc}") from exc

    version.learning_objectives.clear()
    version.questions.clear()
    db.flush()

    for index, text in enumerate(assessment.learningObjectives, start=1):
        version.learning_objectives.append(LearningObjective(text=text, sort_order=index))

    accepted_questions = 0
    for generated_question in assessment.questions:
        if len(generated_question.options) != 4:
            continue
        if sum(1 for option in generated_question.options if option.isCorrect) != 1:
            continue
        q_index = accepted_questions + 1
        question = Question(
            type=generated_question.type,
            text=generated_question.question,
            topic=generated_question.topic,
            difficulty=generated_question.difficulty,
            hint=generated_question.hint,
            explanation=generated_question.explanation,
            source_start_seconds=generated_question.sourceStartSeconds,
            source_end_seconds=generated_question.sourceEndSeconds,
            status="DRAFT",
            sort_order=q_index,
        )
        for o_index, option in enumerate(generated_question.options, start=1):
            question.options.append(
                QuestionOption(text=option.text, is_correct=option.isCorrect, sort_order=o_index)
            )
        version.questions.append(question)
        accepted_questions += 1

    if accepted_questions != payload.question_count:
        version.questions.clear()
        version.status = "DRAFT"
        course.status = "DRAFT"
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="Assessment generation did not return a valid grounded question set. Try generating again.",
        )

    version.status = "READY"
    course.status = "READY"
    log_audit(
        db,
        organization_id=actor.organization_id,
        actor_user_id=actor.user.id,
        action="AI_GENERATION_COMPLETED",
        entity_type="training_version",
        entity_id=version.id,
        metadata={"question_count": len(version.questions)},
    )
    db.commit()
    return get_training(training_id, db, actor)


@router.patch("/questions/{question_id}", response_model=QuestionAdminOut)
def update_question(question_id, payload: UpdateQuestionIn, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    question = db.execute(
        select(Question)
        .join(TrainingVersion, TrainingVersion.id == Question.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .where(Question.id == question_id, TrainingCourse.organization_id == actor.organization_id)
        .options(selectinload(Question.options))
    ).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(question, field, value)
    db.commit()
    db.refresh(question)
    return QuestionAdminOut.model_validate(question)


@router.post("/training/{training_id}/publish", response_model=TrainingDetailOut)
def publish_training(training_id, payload: PublishTrainingIn, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    course = db.execute(
        select(TrainingCourse)
        .where(TrainingCourse.id == training_id, TrainingCourse.organization_id == actor.organization_id)
        .options(selectinload(TrainingCourse.versions).selectinload(TrainingVersion.questions))
    ).scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Training not found")
    version = course.versions[-1]
    if version.status == "PUBLISHED":
        raise HTTPException(status_code=400, detail="Training has already been published.")
    if version.status != "READY" or not version.questions:
        raise HTTPException(status_code=400, detail="Training must be READY with questions before publishing")
    for question in version.questions:
        question.status = "APPROVED"
    version.status = "PUBLISHED"
    version.published_at = datetime.now(timezone.utc)
    course.status = "PUBLISHED"

    recipient_ids = list(dict.fromkeys(payload.recipient_user_ids))
    if payload.assign_to_all:
        recipient_ids = db.execute(
            select(User.id)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == actor.organization_id,
                OrganizationMember.status == "ACTIVE",
                OrganizationMember.role == "EMPLOYEE",
            )
            .order_by(User.name)
        ).scalars().all()

    if recipient_ids:
        recipients = db.execute(
            select(User)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                User.id.in_(recipient_ids),
                OrganizationMember.organization_id == actor.organization_id,
                OrganizationMember.status == "ACTIVE",
                OrganizationMember.role == "EMPLOYEE",
            )
        ).scalars().all()
        now = datetime.now(timezone.utc)
        assignment = Assignment(
            organization_id=actor.organization_id,
            training_version_id=version.id,
            name=course.title,
            passing_score=80,
            required_watch_percentage=90,
            max_attempts_per_question=2,
            allow_retakes=False,
            created_by=actor.user.id,
        )
        for user_id in recipient_ids:
            assignment.recipients.append(
                AssignmentRecipient(user_id=user_id, status="NOT_STARTED", assigned_at=now)
            )
        db.add(assignment)
        db.flush()
        notify_assignment_recipients(
            db,
            organization_id=actor.organization_id,
            recipients=recipients,
            assignment_id=assignment.id,
            assignment_name=assignment.name,
            training_title=course.title,
            due_at_label=None,
        )
    log_audit(
        db,
        organization_id=actor.organization_id,
        actor_user_id=actor.user.id,
        action="TRAINING_PUBLISHED",
        entity_type="training_version",
        entity_id=version.id,
        metadata={"recipient_count": len(recipient_ids)},
    )
    db.commit()
    return get_training(training_id, db, actor)


@router.delete("/training/{training_id}", response_model=APIMessage)
def delete_training(training_id, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    course = db.execute(
        select(TrainingCourse)
        .where(TrainingCourse.id == training_id, TrainingCourse.organization_id == actor.organization_id)
        .options(selectinload(TrainingCourse.versions))
    ).scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Training not found")

    generated_source_urls: list[str] = []
    for version in course.versions:
        for source in version.content_sources:
            if source.source_type == "GENERATED_VIDEO":
                generated_source_urls.append(source.source_url or "")

    version_ids = [version.id for version in course.versions]
    if version_ids:
        assignments = db.execute(
            select(Assignment)
            .where(Assignment.training_version_id.in_(version_ids))
            .options(selectinload(Assignment.recipients))
        ).scalars().all()
        assignment_ids = [assignment.id for assignment in assignments]
        recipient_ids = [recipient.id for assignment in assignments for recipient in assignment.recipients]

        if recipient_ids:
            training_sessions = db.execute(
                select(TrainingSession)
                .where(TrainingSession.assignment_recipient_id.in_(recipient_ids))
                .options(
                    selectinload(TrainingSession.quiz_sessions).selectinload(QuizSession.attempts),
                    selectinload(TrainingSession.quiz_sessions).selectinload(QuizSession.summaries),
                    selectinload(TrainingSession.video_progress_records).selectinload(VideoProgress.intervals),
                )
            ).scalars().all()
            for training_session in training_sessions:
                db.delete(training_session)
            db.flush()

        if assignment_ids:
            assignment_links = {f"/learn/{assignment_id}" for assignment_id in assignment_ids}
            assignment_id_strings = {str(assignment_id) for assignment_id in assignment_ids}
            notifications = db.execute(
                select(Notification).where(Notification.organization_id == actor.organization_id)
            ).scalars().all()
            for notification in notifications:
                metadata_assignment_id = str((notification.metadata_json or {}).get("assignment_id") or "")
                if notification.link_url in assignment_links or metadata_assignment_id in assignment_id_strings:
                    db.delete(notification)
            db.flush()

        for assignment in assignments:
            db.delete(assignment)
        db.flush()

    title = course.title
    db.delete(course)
    log_audit(
        db,
        organization_id=actor.organization_id,
        actor_user_id=actor.user.id,
        action="TRAINING_DELETED",
        entity_type="training_course",
        entity_id=course.id,
        metadata={"title": title},
    )
    db.commit()
    for source_url in generated_source_urls:
        remove_generated_training_assets(source_url)
    return APIMessage(message="Training deleted.")
