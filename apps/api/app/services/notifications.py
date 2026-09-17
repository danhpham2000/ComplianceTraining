from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Notification, OrganizationMember, User
from app.services.email import (
    send_assignment_email,
    send_certificate_email,
    send_completion_email,
    send_training_failed_email,
    send_training_ready_email,
)

settings = get_settings()


def create_notification(
    db: Session,
    *,
    organization_id,
    user_id,
    type: str,
    title: str,
    body: str,
    link_url: str | None = None,
    metadata_json: dict | None = None,
) -> Notification:
    notification = Notification(
        organization_id=organization_id,
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link_url=link_url,
        metadata_json=metadata_json,
    )
    db.add(notification)
    db.flush()
    return notification


def list_notifications(db: Session, *, organization_id, user_id) -> list[Notification]:
    return db.execute(
        select(Notification)
        .where(Notification.organization_id == organization_id, Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(20)
    ).scalars().all()


def mark_notifications_read(db: Session, *, organization_id, user_id, notification_ids: Iterable | None = None) -> int:
    rows = db.execute(
        select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
        )
    ).scalars().all()
    target_ids = None if notification_ids is None else {str(item) for item in notification_ids}
    now = datetime.now(timezone.utc)
    updated = 0
    for notification in rows:
        if notification.is_read:
            continue
        if target_ids is not None and str(notification.id) not in target_ids:
            continue
        notification.is_read = True
        notification.read_at = now
        updated += 1
    if updated:
        db.flush()
    return updated


def notify_assignment_recipients(
    db: Session,
    *,
    organization_id,
    recipients: list[User],
    assignment_id,
    assignment_name: str,
    training_title: str,
    due_at_label: str | None,
) -> None:
    for recipient in recipients:
        action_url = f"{settings.web_app_url.rstrip('/')}/learn/{assignment_id}"
        delivery_error = send_assignment_email(
            email=recipient.email,
            recipient_name=recipient.name,
            assignment_name=assignment_name,
            training_title=training_title,
            due_at=due_at_label,
            action_url=action_url,
        )
        create_notification(
            db,
            organization_id=organization_id,
            user_id=recipient.id,
            type="ASSIGNMENT_ASSIGNED",
            title="New assignment received",
            body=f"{assignment_name} has been assigned to you.",
            link_url=f"/learn/{assignment_id}",
            metadata_json={
                "assignment_name": assignment_name,
                "training_title": training_title,
                "delivery_error": delivery_error,
            }
            if delivery_error
            else {
                "assignment_name": assignment_name,
                "training_title": training_title,
            },
        )


def notify_assignment_completed(
    db: Session,
    *,
    organization_id,
    employee: User,
    assignment_id,
    assignment_name: str,
    training_title: str,
    score: float | None,
) -> None:
    employee_action_url = f"{settings.web_app_url.rstrip('/')}/learn/{assignment_id}?tab=summary"
    employee_delivery_error = send_certificate_email(
        email=employee.email,
        employee_name=employee.name,
        assignment_name=assignment_name,
        training_title=training_title,
        score=score,
        action_url=employee_action_url,
    )
    create_notification(
        db,
        organization_id=organization_id,
        user_id=employee.id,
        type="CERTIFICATE_READY",
        title="Certificate ready",
        body=f"You completed {assignment_name}. Your certificate is now available.",
        link_url=f"/learn/{assignment_id}?tab=summary",
        metadata_json={
            "assignment_id": str(assignment_id),
            "assignment_name": assignment_name,
            "training_title": training_title,
            "score": score,
            "delivery_error": employee_delivery_error,
        }
        if employee_delivery_error
        else {
            "assignment_id": str(assignment_id),
            "assignment_name": assignment_name,
            "training_title": training_title,
            "score": score,
        },
    )

    admins = db.execute(
        select(User)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "ACTIVE",
            OrganizationMember.role.in_(["OWNER", "ADMIN", "MANAGER"]),
        )
        .order_by(User.name)
    ).scalars().all()

    for admin in admins:
        delivery_error = send_completion_email(
            email=admin.email,
            admin_name=admin.name,
            employee_name=employee.name or employee.email,
            assignment_name=assignment_name,
            training_title=training_title,
            score=score,
            action_url=f"{settings.web_app_url.rstrip('/')}/dashboard",
        )
        create_notification(
            db,
            organization_id=organization_id,
            user_id=admin.id,
            type="ASSIGNMENT_COMPLETED",
            title="Assignment completed",
            body=f"{employee.name or employee.email} completed {assignment_name}.",
            link_url="/dashboard",
            metadata_json={
                "assignment_id": str(assignment_id),
                "assignment_name": assignment_name,
                "training_title": training_title,
                "employee_email": employee.email,
                "score": score,
                "delivery_error": delivery_error,
            }
            if delivery_error
            else {
                "assignment_id": str(assignment_id),
                "assignment_name": assignment_name,
                "training_title": training_title,
                "employee_email": employee.email,
                "score": score,
            },
        )


def notify_training_build_completed(
    db: Session,
    *,
    organization_id,
    training_id,
    training_title: str,
) -> None:
    admins = db.execute(
        select(User)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "ACTIVE",
            OrganizationMember.role.in_(["OWNER", "ADMIN", "MANAGER"]),
        )
        .order_by(User.name)
    ).scalars().all()

    for admin in admins:
        action_url = f"{settings.web_app_url.rstrip('/')}/training/{training_id}"
        delivery_error = send_training_ready_email(
            email=admin.email,
            admin_name=admin.name,
            training_title=training_title,
            action_url=action_url,
        )
        create_notification(
            db,
            organization_id=organization_id,
            user_id=admin.id,
            type="TRAINING_BUILD_COMPLETED",
            title="Training ready",
            body=f"{training_title} is ready to review and publish.",
            link_url=f"/training/{training_id}",
            metadata_json={
                "training_id": str(training_id),
                "training_title": training_title,
                "delivery_error": delivery_error,
            }
            if delivery_error
            else {
                "training_id": str(training_id),
                "training_title": training_title,
            },
        )


def notify_training_build_failed(
    db: Session,
    *,
    organization_id,
    training_id,
    training_title: str,
    error_message: str,
) -> None:
    admins = db.execute(
        select(User)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "ACTIVE",
            OrganizationMember.role.in_(["OWNER", "ADMIN", "MANAGER"]),
        )
        .order_by(User.name)
    ).scalars().all()

    short_error = error_message[:220].strip()
    for admin in admins:
        action_url = f"{settings.web_app_url.rstrip('/')}/training/{training_id}"
        delivery_error = send_training_failed_email(
            email=admin.email,
            admin_name=admin.name,
            training_title=training_title,
            error_message=short_error,
            action_url=action_url,
        )
        create_notification(
            db,
            organization_id=organization_id,
            user_id=admin.id,
            type="TRAINING_BUILD_FAILED",
            title="Training build failed",
            body=f"{training_title} could not be completed. Review the error and try again.",
            link_url=f"/training/{training_id}",
            metadata_json={
                "training_id": str(training_id),
                "training_title": training_title,
                "error": short_error,
                "delivery_error": delivery_error,
            }
            if delivery_error
            else {
                "training_id": str(training_id),
                "training_title": training_title,
                "error": short_error,
            },
        )
