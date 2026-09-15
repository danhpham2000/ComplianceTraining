from fastapi import APIRouter

from app.api.deps import CurrentActor, DBSession
from app.schemas.admin import NotificationOut, NotificationReadIn
from app.schemas.common import APIMessage
from app.services.notifications import list_notifications, mark_notifications_read


router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationOut])
def get_notifications(db: DBSession, actor: CurrentActor):
    return list_notifications(
        db,
        organization_id=actor.organization_id,
        user_id=actor.user.id,
    )


@router.post("/notifications/read", response_model=APIMessage)
def read_notifications(payload: NotificationReadIn, db: DBSession, actor: CurrentActor):
    updated = mark_notifications_read(
        db,
        organization_id=actor.organization_id,
        user_id=actor.user.id,
        notification_ids=None if payload.mark_all else payload.notification_ids,
    )
    db.commit()
    return APIMessage(message=f"Marked {updated} notification(s) as read.")
