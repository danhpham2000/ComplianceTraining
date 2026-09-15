from statistics import mean

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentActor, DBSession
from app.models import Assignment, AssignmentRecipient, Organization, Question, QuestionAttempt, TrainingCourse, TrainingVersion, User
from app.schemas.common import CertificateOut, LearnerProgressOut, OverviewMetricsOut, TopicMetricOut
from app.services.auth import require_roles
from app.services.certificates import CertificateContext, render_certificate_pdf


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewMetricsOut)
def overview(db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    recipients = db.execute(
        select(AssignmentRecipient)
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .where(Assignment.organization_id == actor.organization_id)
    ).scalars().all()
    total = len(recipients)
    completed = [item for item in recipients if item.status == "COMPLETED"]
    in_progress = [item for item in recipients if item.status in {"IN_PROGRESS", "QUIZ_READY"}]
    failed = [item for item in recipients if item.status == "FAILED"]
    not_started = [item for item in recipients if item.status == "NOT_STARTED"]
    overdue = [
        item for item in recipients
        if item.status == "OVERDUE"
    ]
    return OverviewMetricsOut(
        total_assigned=total,
        not_started=len(not_started),
        in_progress=len(in_progress),
        completed=len(completed),
        failed=len(failed),
        overdue=len(overdue),
        completion_rate=round((len(completed) / total * 100), 2) if total else 0,
        average_score=round(mean([item.final_score for item in completed if item.final_score is not None]), 2) if completed else 0,
        average_first_attempt_accuracy=round(
            mean([item.first_attempt_accuracy for item in recipients if item.first_attempt_accuracy is not None]),
            2,
        )
        if recipients
        else 0,
        average_final_accuracy=round(
            mean([item.final_accuracy for item in recipients if item.final_accuracy is not None]),
            2,
        )
        if recipients
        else 0,
    )


@router.get("/topics", response_model=list[TopicMetricOut])
def topics(db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    questions = db.execute(
        select(Question)
        .join(TrainingVersion, TrainingVersion.id == Question.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .where(TrainingCourse.organization_id == actor.organization_id)
    ).scalars().all()
    attempts = db.execute(
        select(QuestionAttempt)
        .join(Question, Question.id == QuestionAttempt.question_id)
        .join(TrainingVersion, TrainingVersion.id == Question.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .where(TrainingCourse.organization_id == actor.organization_id)
        .order_by(QuestionAttempt.question_id, QuestionAttempt.attempt_number)
    ).scalars().all()
    by_question = {}
    for attempt in attempts:
        by_question.setdefault(attempt.question_id, []).append(attempt)
    metrics = []
    for topic in sorted({question.topic or "Uncategorized" for question in questions}):
        topic_questions = [question for question in questions if (question.topic or "Uncategorized") == topic]
        first_correct = 0
        final_correct = 0
        failures = 0
        answered = 0
        for question in topic_questions:
            question_attempts = by_question.get(question.id, [])
            if not question_attempts:
                continue
            answered += 1
            if question_attempts[0].is_correct:
                first_correct += 1
            if question_attempts[-1].is_correct:
                final_correct += 1
            else:
                failures += 1
        if not answered:
            continue
        metrics.append(
            TopicMetricOut(
                topic=topic,
                questions_answered=answered,
                first_attempt_accuracy=round(first_correct / answered * 100, 2),
                final_accuracy=round(final_correct / answered * 100, 2),
                failure_rate=round(failures / answered * 100, 2),
            )
        )
    return metrics


@router.get("/learner-progress", response_model=list[LearnerProgressOut])
def learner_progress(db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    rows = db.execute(
        select(AssignmentRecipient, Assignment, TrainingCourse.title, User)
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .join(TrainingVersion, TrainingVersion.id == Assignment.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .join(User, User.id == AssignmentRecipient.user_id)
        .where(Assignment.organization_id == actor.organization_id)
        .order_by(AssignmentRecipient.completed_at.is_(None), AssignmentRecipient.completed_at.desc(), AssignmentRecipient.assigned_at.desc())
    ).all()

    payload: list[LearnerProgressOut] = []
    for recipient, assignment, training_title, user in rows:
        certificate = None
        if recipient.status == "COMPLETED" and recipient.completed_at:
            certificate = CertificateOut(
                certificate_number=CertificateContext(
                    assignment_id=assignment.id,
                    assignment_recipient_id=recipient.id,
                    organization_name=actor.organization.name,
                    employee_name=user.name or user.email,
                    employee_email=user.email,
                    assignment_name=assignment.name,
                    training_title=training_title,
                    completed_at=recipient.completed_at,
                    score=recipient.final_score,
                ).certificate_number,
                issued_at=recipient.completed_at,
                employee_name=user.name or user.email,
                employee_email=user.email,
                training_title=training_title,
                assignment_name=assignment.name,
                score=recipient.final_score,
                download_path=f"/analytics/learner-progress/{recipient.id}/certificate",
            )

        payload.append(
            LearnerProgressOut(
                assignment_recipient_id=recipient.id,
                assignment_id=assignment.id,
                employee_id=user.id,
                employee_name=user.name or user.email,
                employee_email=user.email,
                assignment_name=assignment.name,
                training_title=training_title,
                status=recipient.status,
                due_at=assignment.due_at,
                started_at=recipient.started_at,
                completed_at=recipient.completed_at,
                final_score=recipient.final_score,
                certificate=certificate,
            )
        )
    return payload


@router.get("/learner-progress/{assignment_recipient_id}/certificate")
def download_certificate(assignment_recipient_id, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    row = db.execute(
        select(AssignmentRecipient, Assignment, TrainingCourse.title, User, Organization.name)
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .join(TrainingVersion, TrainingVersion.id == Assignment.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .join(User, User.id == AssignmentRecipient.user_id)
        .join(Organization, Organization.id == Assignment.organization_id)
        .where(
            AssignmentRecipient.id == assignment_recipient_id,
            Assignment.organization_id == actor.organization_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found")

    recipient, assignment, training_title, user, organization_name = row
    if recipient.status != "COMPLETED" or not recipient.completed_at:
        raise HTTPException(status_code=400, detail="Certificate is available after successful completion")

    context = CertificateContext(
        assignment_id=assignment.id,
        assignment_recipient_id=recipient.id,
        organization_name=organization_name,
        employee_name=user.name or user.email,
        employee_email=user.email,
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
