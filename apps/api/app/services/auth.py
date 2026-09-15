from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AuthSession, OrganizationMember, User
from app.services.security import hash_secret


@dataclass
class Actor:
    user: User
    membership: OrganizationMember
    session: AuthSession | None = None

    @property
    def organization_id(self):
        return self.membership.organization_id

    @property
    def organization(self):
        return self.membership.organization

    @property
    def role(self) -> str:
        return self.membership.role


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header.")
    return token.strip()


def get_current_actor(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    token = parse_bearer_token(authorization)
    stmt = (
        select(AuthSession, User, OrganizationMember)
        .join(User, User.id == AuthSession.user_id)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(AuthSession.token_hash == hash_secret(token))
        .where(AuthSession.revoked_at.is_(None))
        .where(AuthSession.expires_at > datetime.now(timezone.utc))
        .where(OrganizationMember.status == "ACTIVE")
        .order_by(OrganizationMember.joined_at.desc().nullslast())
    )
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid.")

    session, user, membership = row
    if not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email verification required.")

    return Actor(user=user, membership=membership, session=session)


def require_roles(actor: Actor, *roles: str) -> None:
    if actor.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
