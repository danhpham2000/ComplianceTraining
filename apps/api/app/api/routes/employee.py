from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentActor, DBSession
from app.models import (
    Assignment,
    AssignmentRecipient,
    ContentSource,
    Organization,
    Question,
    QuestionOption,
    QuizSession,
    TrainingCourse,
    TrainingSummary,
    TrainingVersion,
)
from app.schemas.employee import (
    AssignmentDetailOut,
    AssignmentSummaryOut,
    QuestionAttemptIn,
    QuestionAttemptResultOut,
    QuizStartOut,
    ResultOut,
    TrainingSummaryOut,
    VideoProgressIn,
    VideoProgressOut,
)
from app.services.auth import require_roles
from app.services.certificates import CertificateContext, render_certificate_pdf
from app.services.notifications import notify_assignment_completed
from app.services.progress import record_video_progress
from app.services.quiz import (
    build_employee_questions,
    finalize_quiz,
    get_or_create_training_session,
    start_quiz,
    submit_attempt,
)


router = APIRouter(tags=["employee"])


def _build_certificate(recipient, assignment, training_title: str, user, organization_name: str = "NextPhase"):
    if recipient.status != "COMPLETED" or not recipient.completed_at:
        return None
    employee_name = user.name or user.email
    return {
        "certificate_number": CertificateContext(
            assignment_id=assignment.id,
            assignment_recipient_id=recipient.id,
            organization_name=organization_name,
            employee_name=employee_name,
            employee_email=user.email,
            assignment_name=assignment.name,
            training_title=training_title,
            completed_at=recipient.completed_at,
            score=recipient.final_score,
        ).certificate_number,
        "issued_at": recipient.completed_at,
        "employee_name": employee_name,
        "employee_email": user.email,
        "training_title": training_title,
        "assignment_name": assignment.name,
        "score": recipient.final_score,
        "download_path": f"/me/assignments/{assignment.id}/certificate",
    }


def _get_recipient(db, actor, assignment_id):
    row = db.execute(
        select(AssignmentRecipient, Assignment, TrainingCourse.title, TrainingCourse.description, ContentSource)
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .join(TrainingVersion, TrainingVersion.id == Assignment.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .outerjoin(ContentSource, ContentSource.training_version_id == TrainingVersion.id)
        .where(AssignmentRecipient.assignment_id == assignment_id, AssignmentRecipient.user_id == actor.user.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return row


@router.get("/me/assignments", response_model=list[AssignmentSummaryOut])
def my_assignments(db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER", "EMPLOYEE")
    rows = db.execute(
        select(AssignmentRecipient, Assignment, TrainingCourse.title)
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .join(TrainingVersion, TrainingVersion.id == Assignment.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .where(AssignmentRecipient.user_id == actor.user.id)
        .order_by(Assignment.due_at.is_(None), Assignment.due_at.asc())
    ).all()
    return [
        AssignmentSummaryOut(
            id=assignment.id,
            name=assignment.name,
            status=recipient.status,
            training_title=title,
            due_at=assignment.due_at,
            start_at=assignment.start_at,
            passing_score=assignment.passing_score,
            required_watch_percentage=assignment.required_watch_percentage,
            max_attempts_per_question=assignment.max_attempts_per_question,
            final_score=recipient.final_score,
            completed_at=recipient.completed_at,
            certificate=_build_certificate(recipient, assignment, title, actor.user, actor.organization.name),
        )
        for recipient, assignment, title in rows
    ]


@router.get("/me/assignments/{assignment_id}", response_model=AssignmentDetailOut)
def assignment_detail(assignment_id, db: DBSession, actor: CurrentActor):
    recipient, assignment, title, description, source = _get_recipient(db, actor, assignment_id)
    training_session = get_or_create_training_session(db, recipient)
    watch_percentage = 0
    if source:
        from app.models import VideoProgress

        progress = db.execute(
            select(VideoProgress).where(
                VideoProgress.training_session_id == training_session.id,
                VideoProgress.content_source_id == source.id,
            )
        ).scalar_one_or_none()
        watch_percentage = progress.watch_percentage if progress else 0
    db.commit()
    return AssignmentDetailOut(
        id=assignment.id,
        assignment_recipient_id=recipient.id,
        name=assignment.name,
        status=recipient.status,
        training_title=title,
        description=description,
        due_at=assignment.due_at,
        start_at=assignment.start_at,
        passing_score=assignment.passing_score,
        required_watch_percentage=assignment.required_watch_percentage,
        max_attempts_per_question=assignment.max_attempts_per_question,
        watch_percentage=watch_percentage,
        final_score=recipient.final_score,
        completed_at=recipient.completed_at,
        video_url=source.source_url if source else None,
        video_title=source.title if source else None,
        video_duration_seconds=source.duration_seconds if source else None,
        quiz_ready=watch_percentage >= assignment.required_watch_percentage,
        certificate=_build_certificate(recipient, assignment, title, actor.user, actor.organization.name),
    )


@router.post("/me/assignments/{assignment_id}/start", response_model=AssignmentDetailOut)
def start_assignment(assignment_id, db: DBSession, actor: CurrentActor):
    recipient, *_ = _get_recipient(db, actor, assignment_id)
    get_or_create_training_session(db, recipient)
    db.commit()
    return assignment_detail(assignment_id, db, actor)


@router.post("/me/assignments/{assignment_id}/video-progress", response_model=VideoProgressOut)
def push_progress(assignment_id, payload: VideoProgressIn, db: DBSession, actor: CurrentActor):
    recipient, assignment, _, _, source = _get_recipient(db, actor, assignment_id)
    if not source:
        raise HTTPException(status_code=400, detail="Assignment has no video source")
    actual_duration = payload.duration_seconds or source.duration_seconds
    if payload.duration_seconds and source.duration_seconds != payload.duration_seconds:
        source.duration_seconds = payload.duration_seconds
    training_session = get_or_create_training_session(db, recipient)
    progress = record_video_progress(
        db,
        training_session_id=training_session.id,
        content_source_id=source.id,
        duration_seconds=actual_duration,
        start_second=payload.start_second,
        end_second=payload.end_second,
        current_position_seconds=payload.current_position_seconds,
    )
    if progress.watch_percentage >= assignment.required_watch_percentage and recipient.status == "IN_PROGRESS":
        recipient.status = "QUIZ_READY"
    training_session.last_activity_at = datetime.now(timezone.utc)
    db.commit()
    return VideoProgressOut(
        unique_watched_seconds=progress.unique_watched_seconds,
        furthest_position_seconds=progress.furthest_position_seconds,
        watch_percentage=progress.watch_percentage,
    )


@router.post("/me/assignments/{assignment_id}/quiz/start", response_model=QuizStartOut)
def begin_quiz(assignment_id, db: DBSession, actor: CurrentActor):
    recipient, assignment, _, _, source = _get_recipient(db, actor, assignment_id)
    if not source:
        raise HTTPException(status_code=400, detail="Assignment has no video source")
    training_session = get_or_create_training_session(db, recipient)
    quiz_session, questions = start_quiz(
        db,
        assignment=assignment,
        recipient=recipient,
        training_session=training_session,
        content_source=source,
    )
    db.commit()
    return QuizStartOut(
        quiz_session_id=quiz_session.id,
        assignment_id=assignment.id,
        max_attempts_per_question=assignment.max_attempts_per_question,
        questions=questions,
    )


@router.post("/me/assignments/{assignment_id}/questions/{question_id}/attempt", response_model=QuestionAttemptResultOut)
def attempt_question(assignment_id, question_id, payload: QuestionAttemptIn, db: DBSession, actor: CurrentActor):
    recipient, assignment, _, _, source = _get_recipient(db, actor, assignment_id)
    training_session = get_or_create_training_session(db, recipient)
    quiz_session = db.execute(
        select(QuizSession).where(QuizSession.training_session_id == training_session.id)
    ).scalar_one_or_none()
    if not quiz_session:
        raise HTTPException(status_code=400, detail="Quiz has not started")
    question = db.execute(
        select(Question)
        .where(Question.id == question_id, Question.training_version_id == assignment.training_version_id)
        .options(selectinload(Question.options))
    ).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    option = next((item for item in question.options if item.id == payload.option_id), None)
    if not option:
        raise HTTPException(status_code=400, detail="Invalid option")
    result = submit_attempt(
        db,
        assignment=assignment,
        quiz_session=quiz_session,
        question=question,
        option=option,
        idempotency_key=payload.idempotency_key,
    )
    training_session.last_activity_at = datetime.now(timezone.utc)
    db.commit()
    return QuestionAttemptResultOut(**result)


@router.post("/me/assignments/{assignment_id}/quiz/complete", response_model=ResultOut)
def complete_quiz(assignment_id, db: DBSession, actor: CurrentActor):
    recipient, assignment, title, _, source = _get_recipient(db, actor, assignment_id)
    training_session = get_or_create_training_session(db, recipient)
    quiz_session = db.execute(
        select(QuizSession)
        .where(QuizSession.training_session_id == training_session.id)
        .options(selectinload(QuizSession.attempts), selectinload(QuizSession.summaries))
    ).scalar_one_or_none()
    if not quiz_session:
        raise HTTPException(status_code=400, detail="Quiz has not started")
    was_completed = recipient.status == "COMPLETED"
    questions = db.execute(
        select(Question)
        .where(Question.training_version_id == assignment.training_version_id)
        .options(selectinload(Question.options))
        .order_by(Question.sort_order)
    ).scalars().all()
    result = finalize_quiz(
        db,
        assignment=assignment,
        recipient=recipient,
        training_session=training_session,
        quiz_session=quiz_session,
        questions=questions,
        content_source=source,
    )
    if result["status"] == "COMPLETED" and not was_completed:
        notify_assignment_completed(
            db,
            organization_id=actor.organization_id,
            employee=actor.user,
            assignment_id=assignment.id,
            assignment_name=assignment.name,
            training_title=title,
            score=recipient.final_score,
        )
    db.commit()
    return result_page(assignment_id, db, actor)


@router.get("/me/assignments/{assignment_id}/result", response_model=ResultOut)
def result_page(assignment_id, db: DBSession, actor: CurrentActor):
    recipient, assignment, training_title, _, source = _get_recipient(db, actor, assignment_id)
    training_session = get_or_create_training_session(db, recipient)
    quiz_session = db.execute(
        select(QuizSession)
        .where(QuizSession.training_session_id == training_session.id)
        .options(selectinload(QuizSession.attempts), selectinload(QuizSession.summaries))
    ).scalar_one_or_none()
    questions = db.execute(
        select(Question)
        .where(Question.training_version_id == assignment.training_version_id)
        .options(selectinload(Question.options))
        .order_by(Question.sort_order)
    ).scalars().all()
    breakdown = build_employee_questions(
        questions,
        quiz_session.attempts if quiz_session else [],
        assignment.max_attempts_per_question,
    )
    summary = quiz_session.summaries[-1] if quiz_session and quiz_session.summaries else None
    progress = None
    if source:
        from app.models import VideoProgress

        progress = db.execute(
            select(VideoProgress).where(
                VideoProgress.training_session_id == training_session.id,
                VideoProgress.content_source_id == source.id,
            )
        ).scalar_one_or_none()
    return ResultOut(
        status=recipient.status,
        completed_at=recipient.completed_at,
        official_score=recipient.final_score,
        passing_score=assignment.passing_score,
        first_attempt_accuracy=recipient.first_attempt_accuracy,
        final_accuracy=recipient.final_accuracy,
        video_completion_percentage=progress.watch_percentage if progress else 0,
        summary=TrainingSummaryOut(
            strengths=summary.strengths_json or [],
            needs_improvement=summary.needs_improvement_json or [],
            recommended_review=summary.recommended_review_json or [],
            summary=summary.summary_text,
        )
        if summary
        else None,
        question_breakdown=breakdown,
        certificate=_build_certificate(recipient, assignment, training_title, actor.user, actor.organization.name),
    )


@router.get("/me/assignments/{assignment_id}/certificate")
def download_certificate(assignment_id, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER", "EMPLOYEE")
    row = db.execute(
        select(AssignmentRecipient, Assignment, TrainingCourse.title, Organization.name)
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .join(TrainingVersion, TrainingVersion.id == Assignment.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .join(Organization, Organization.id == Assignment.organization_id)
        .where(AssignmentRecipient.assignment_id == assignment_id, AssignmentRecipient.user_id == actor.user.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")

    recipient, assignment, training_title, organization_name = row
    if recipient.status != "COMPLETED" or not recipient.completed_at:
        raise HTTPException(status_code=400, detail="Certificate is available after successful completion")

    context = CertificateContext(
        assignment_id=assignment.id,
        assignment_recipient_id=recipient.id,
        organization_name=organization_name,
        employee_name=actor.user.name or actor.user.email,
        employee_email=actor.user.email,
        assignment_name=assignment.name,
        training_title=training_title,
        completed_at=recipient.completed_at,
        score=recipient.final_score,
    )
    pdf_bytes = render_certificate_pdf(context)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{context.filename}"',
            "Cache-Control": "no-store",
        },
    )
