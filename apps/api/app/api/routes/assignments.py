from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentActor, DBSession
from app.models import Assignment, AssignmentRecipient, OrganizationMember, TrainingCourse, TrainingVersion, User
from app.schemas.admin import AssignmentAdminDetailOut, AssignmentCreateIn
from app.schemas.common import AssignmentSummaryOut
from app.services.audit import log_audit
from app.services.notifications import notify_assignment_recipients
from app.services.auth import require_roles


router = APIRouter(tags=["assignments"])


@router.get("/assignments", response_model=list[AssignmentSummaryOut])
def list_assignments(db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    assignments = db.execute(
        select(Assignment, TrainingCourse.title)
        .join(TrainingVersion, TrainingVersion.id == Assignment.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .where(Assignment.organization_id == actor.organization_id)
        .order_by(Assignment.created_at.desc())
    ).all()
    return [
        AssignmentSummaryOut(
            id=assignment.id,
            name=assignment.name,
            training_title=title,
            due_at=assignment.due_at,
            start_at=assignment.start_at,
            passing_score=assignment.passing_score,
            required_watch_percentage=assignment.required_watch_percentage,
            max_attempts_per_question=assignment.max_attempts_per_question,
        )
        for assignment, title in assignments
    ]


@router.post("/assignments", response_model=AssignmentAdminDetailOut)
def create_assignment(payload: AssignmentCreateIn, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN")
    if payload.due_at and payload.start_at and payload.due_at < payload.start_at:
        raise HTTPException(status_code=400, detail="due_at must be greater than or equal to start_at")
    row = db.execute(
        select(TrainingVersion, TrainingCourse.title)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .where(
            TrainingVersion.id == payload.training_version_id,
            TrainingCourse.organization_id == actor.organization_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=400, detail="Only published training can be assigned")
    version, training_title = row
    if not version or version.status != "PUBLISHED":
        raise HTTPException(status_code=400, detail="Only published training can be assigned")

    recipient_ids = list(dict.fromkeys(payload.recipient_user_ids))
    if payload.assign_to_all:
        recipient_ids = db.execute(
            select(User.id)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == actor.organization_id,
                OrganizationMember.status == "ACTIVE",
                OrganizationMember.role.in_(["MANAGER", "EMPLOYEE"]),
            )
            .order_by(User.name)
        ).scalars().all()

    if not recipient_ids:
        raise HTTPException(status_code=400, detail="Select at least one recipient")

    recipients = db.execute(
        select(User)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(
            User.id.in_(recipient_ids),
            OrganizationMember.organization_id == actor.organization_id,
            OrganizationMember.status == "ACTIVE",
        )
    ).scalars().all()
    if len(recipients) != len(set(recipient_ids)):
        raise HTTPException(status_code=400, detail="One or more recipients are invalid")

    assignment = Assignment(
        organization_id=actor.organization_id,
        training_version_id=payload.training_version_id,
        name=payload.name,
        start_at=payload.start_at,
        due_at=payload.due_at,
        passing_score=payload.passing_score,
        required_watch_percentage=payload.required_watch_percentage,
        max_attempts_per_question=payload.max_attempts_per_question,
        allow_retakes=payload.allow_retakes,
        created_by=actor.user.id,
    )
    now = datetime.now(timezone.utc)
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
        training_title=training_title,
        due_at_label=assignment.due_at.strftime("%b %d, %Y %I:%M %p UTC") if assignment.due_at else None,
    )
    log_audit(
        db,
        organization_id=actor.organization_id,
        actor_user_id=actor.user.id,
        action="ASSIGNMENT_CREATED",
        entity_type="assignment",
        entity_id=assignment.id,
        metadata={"recipient_count": len(recipient_ids)},
    )
    db.commit()
    return get_assignment(assignment.id, db, actor)


@router.get("/assignments/{assignment_id}", response_model=AssignmentAdminDetailOut)
def get_assignment(assignment_id, db: DBSession, actor: CurrentActor):
    require_roles(actor, "OWNER", "ADMIN", "MANAGER")
    row = db.execute(
        select(Assignment, TrainingCourse.title)
        .join(TrainingVersion, TrainingVersion.id == Assignment.training_version_id)
        .join(TrainingCourse, TrainingCourse.id == TrainingVersion.course_id)
        .where(Assignment.id == assignment_id, Assignment.organization_id == actor.organization_id)
        .options(selectinload(Assignment.recipients).selectinload(AssignmentRecipient.user))
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    assignment, title = row
    return AssignmentAdminDetailOut(
        id=assignment.id,
        name=assignment.name,
        training_version_id=assignment.training_version_id,
        training_title=title,
        start_at=assignment.start_at,
        due_at=assignment.due_at,
        passing_score=assignment.passing_score,
        required_watch_percentage=assignment.required_watch_percentage,
        max_attempts_per_question=assignment.max_attempts_per_question,
        allow_retakes=assignment.allow_retakes,
        recipients=[
            {
                "user_id": recipient.user_id,
                "name": recipient.user.name if recipient.user else None,
                "email": recipient.user.email if recipient.user else None,
                "status": recipient.status,
                "assigned_at": recipient.assigned_at,
                "final_score": recipient.final_score,
            }
            for recipient in assignment.recipients
        ],
    )
