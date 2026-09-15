from datetime import datetime, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentActor, DBSession
from app.core.config import get_settings
from app.models import AuthSession, Organization, OrganizationMember, User
from app.schemas.auth import (
    ChangePasswordRequest,
    InviteMemberRequest,
    LoginRequest,
    PendingVerificationOut,
    RegisterRequest,
    ResendVerificationRequest,
    SessionOut,
    UpdatePreferencesRequest,
    UpdateWorkspacePreferencesRequest,
    UpdateDirectoryUserRequest,
    UserPreferencesOut,
    VerifyEmailRequest,
    WorkspacePreferencesOut,
)
from app.schemas.common import APIMessage, ActorSummary, DirectoryUserOut, OrganizationSummary
from app.services.auth import Actor
from app.services.email import send_invitation_email, send_verification_email
from app.services.security import (
    hash_password,
    hash_secret,
    new_session_token,
    new_verification_code,
    normalize_email,
    require_allowed_email,
    session_expiry,
    verification_expiry,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def build_actor_summary(actor: Actor) -> ActorSummary:
    return ActorSummary(
        id=actor.user.id,
        email=actor.user.email,
        name=actor.user.name,
        role=actor.role,
        time_zone=actor.user.time_zone,
        organization=OrganizationSummary(
            id=actor.membership.organization.id,
            name=actor.membership.organization.name,
            slug=actor.membership.organization.slug,
        ),
    )


def create_session(db: DBSession, user: User) -> str:
    token = new_session_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_secret(token),
            expires_at=session_expiry(),
        )
    )
    db.flush()
    return token


def build_pending_response(
    email: str,
    code: str,
    expires_at: datetime,
    *,
    delivery_error: str | None = None,
) -> PendingVerificationOut:
    hint = None
    message = "Verification email sent. Confirm the email before signing in."
    return PendingVerificationOut(
        message=message,
        email=email,
        verification_expires_at=expires_at,
        verification_code_hint=hint,
    )


def get_or_create_default_org(db: DBSession) -> Organization:
    organization = db.execute(
        select(Organization).where(Organization.slug == "nextphase-ai")
    ).scalar_one_or_none()
    if organization:
        return organization

    organization = Organization(name="NextPhase AI", slug="nextphase-ai")
    db.add(organization)
    db.flush()
    return organization


def upsert_membership(db: DBSession, organization_id, user_id, role: str) -> OrganizationMember:
    membership = db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .where(OrganizationMember.user_id == user_id)
    ).scalar_one_or_none()
    if membership:
        membership.role = role
        membership.status = "ACTIVE"
        return membership

    membership = OrganizationMember(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        status="ACTIVE",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(membership)
    db.flush()
    return membership


@router.post("/register", response_model=PendingVerificationOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DBSession):
    email = require_allowed_email(payload.email)
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing and existing.email_verified:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists for this email.")

    code = new_verification_code()
    expires_at = verification_expiry()

    if existing:
        user = existing
        user.name = payload.name.strip()
        user.password_hash = hash_password(payload.password)
        user.email_verified = False
        user.verification_code_hash = hash_secret(code)
        user.verification_code_expires_at = expires_at
    else:
        user = User(
            email=email,
            name=payload.name.strip(),
            password_hash=hash_password(payload.password),
            email_verified=False,
            verification_code_hash=hash_secret(code),
            verification_code_expires_at=expires_at,
        )
        db.add(user)
        db.flush()

    organization = get_or_create_default_org(db)
    existing_membership = db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.user_id == user.id,
        )
    ).scalar_one_or_none()
    target_role = existing_membership.role if existing_membership else payload.role
    upsert_membership(db, organization.id, user.id, target_role)
    db.commit()
    delivery_error = send_verification_email(email, code, expires_at, fail_silently=False)
    return build_pending_response(email, code, expires_at, delivery_error=delivery_error)


@router.post("/resend-verification", response_model=PendingVerificationOut)
def resend_verification(payload: ResendVerificationRequest, db: DBSession):
    email = require_allowed_email(payload.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    if user.email_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already verified.")

    code = new_verification_code()
    expires_at = verification_expiry()
    user.verification_code_hash = hash_secret(code)
    user.verification_code_expires_at = expires_at
    db.commit()
    delivery_error = send_verification_email(email, code, expires_at, fail_silently=False)
    return build_pending_response(email, code, expires_at, delivery_error=delivery_error)


@router.post("/verify-email", response_model=SessionOut)
def verify_email(payload: VerifyEmailRequest, db: DBSession):
    email = require_allowed_email(payload.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    if not user.verification_code_hash or not user.verification_code_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No verification code is active.")
    if user.verification_code_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired.")
    if user.verification_code_hash != hash_secret(payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code is invalid.")

    user.email_verified = True
    user.verification_code_hash = None
    user.verification_code_expires_at = None
    token = create_session(db, user)
    db.commit()
    db.refresh(user)
    membership = db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .where(OrganizationMember.status == "ACTIVE")
        .order_by(OrganizationMember.joined_at.desc().nullslast())
    ).scalars().first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active organization membership found.")
    actor = Actor(user=user, membership=membership)
    return SessionOut(token=token, actor=build_actor_summary(actor))


@router.post("/login", response_model=SessionOut)
def login(payload: LoginRequest, db: DBSession):
    email = require_allowed_email(payload.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    if not user.email_verified:
        code = new_verification_code()
        expires_at = verification_expiry()
        user.verification_code_hash = hash_secret(code)
        user.verification_code_expires_at = expires_at
        db.commit()
        send_verification_email(email, code, expires_at, fail_silently=False)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Email not verified.",
                "email": email,
                "verification_code_hint": None,
            },
        )

    membership = db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .where(OrganizationMember.status == "ACTIVE")
        .order_by(OrganizationMember.joined_at.desc().nullslast())
    ).scalars().first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active organization membership found.")

    token = create_session(db, user)
    db.commit()
    actor = Actor(user=user, membership=membership)
    return SessionOut(token=token, actor=build_actor_summary(actor))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(actor: CurrentActor, db: DBSession):
    if actor.session:
        actor.session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=ActorSummary)
def me(actor: CurrentActor):
    return build_actor_summary(actor)


@router.get("/directory", response_model=list[DirectoryUserOut])
def directory(db: DBSession, actor: CurrentActor):
    rows = db.execute(
        select(User, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == actor.organization_id)
        .order_by(OrganizationMember.role, User.name)
    ).all()
    return [
        DirectoryUserOut(
            id=user.id,
            email=user.email,
            name=user.name,
            time_zone=user.time_zone,
            role=membership.role,
            status=membership.status,
        )
        for user, membership in rows
    ]


@router.post("/invite", response_model=DirectoryUserOut, status_code=status.HTTP_201_CREATED)
def invite_member(payload: InviteMemberRequest, actor: CurrentActor, db: DBSession):
    if actor.role not in {"OWNER", "ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")

    email = require_allowed_email(payload.email)
    existing_user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing_user and existing_user.id == actor.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use the directory to manage your own account.")

    name = payload.name.strip() if payload.name else None
    if existing_user:
        user = existing_user
        if name:
            user.name = name
    else:
        user = User(
            email=email,
            name=name,
            email_verified=False,
        )
        db.add(user)
        db.flush()

    membership = upsert_membership(db, actor.organization_id, user.id, payload.role)
    db.commit()

    query = urlencode(
        {
            "email": user.email,
            "role": membership.role,
            **({"name": user.name} if user.name else {}),
        }
    )
    existing_account = bool(user.email_verified and user.password_hash)
    target_path = "/login" if existing_account else "/register"
    action_url = f"{settings.web_app_url.rstrip('/')}{target_path}?{query}"

    send_invitation_email(
        email=user.email,
        recipient_name=user.name,
        inviter_name=actor.user.name,
        role=membership.role,
        action_url=action_url,
        existing_account=existing_account,
        fail_silently=False,
    )

    return DirectoryUserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        time_zone=user.time_zone,
        role=membership.role,
        status=membership.status,
    )


@router.post("/change-password", response_model=APIMessage)
def change_password(payload: ChangePasswordRequest, actor: CurrentActor, db: DBSession):
    if not verify_password(payload.current_password, actor.user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    actor.user.password_hash = hash_password(payload.new_password)
    db.commit()
    return APIMessage(message="Password updated.")


@router.get("/preferences", response_model=UserPreferencesOut)
def preferences(actor: CurrentActor):
    return UserPreferencesOut(time_zone=actor.user.time_zone)


@router.patch("/preferences", response_model=UserPreferencesOut)
def update_preferences(payload: UpdatePreferencesRequest, actor: CurrentActor, db: DBSession):
    time_zone = payload.time_zone.strip() if payload.time_zone else None
    if time_zone:
        try:
            ZoneInfo(time_zone)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid time zone.") from exc
    actor.user.time_zone = time_zone or None
    db.commit()
    return UserPreferencesOut(time_zone=actor.user.time_zone)


@router.get("/workspace-preferences", response_model=WorkspacePreferencesOut)
def workspace_preferences(actor: CurrentActor, db: DBSession):
    if actor.role not in {"OWNER", "ADMIN", "MANAGER"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace admin access required.")
    organization = db.execute(
        select(Organization).where(Organization.id == actor.organization_id)
    ).scalar_one()
    return WorkspacePreferencesOut(
        ai_script_profile_name=organization.ai_script_profile_name,
        ai_script_markdown=organization.ai_script_markdown,
    )


@router.patch("/workspace-preferences", response_model=WorkspacePreferencesOut)
def update_workspace_preferences(payload: UpdateWorkspacePreferencesRequest, actor: CurrentActor, db: DBSession):
    if actor.role not in {"OWNER", "ADMIN", "MANAGER"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace admin access required.")
    organization = db.execute(
        select(Organization).where(Organization.id == actor.organization_id)
    ).scalar_one()

    profile_name = payload.ai_script_profile_name.strip() if payload.ai_script_profile_name else None
    script_markdown = payload.ai_script_markdown.strip() if payload.ai_script_markdown else None

    organization.ai_script_profile_name = profile_name or None
    organization.ai_script_markdown = script_markdown or None
    db.commit()
    return WorkspacePreferencesOut(
        ai_script_profile_name=organization.ai_script_profile_name,
        ai_script_markdown=organization.ai_script_markdown,
    )


@router.patch("/directory/{user_id}", response_model=DirectoryUserOut)
def update_directory_user(user_id, payload: UpdateDirectoryUserRequest, actor: CurrentActor, db: DBSession):
    if actor.role not in {"OWNER", "ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")

    row = db.execute(
        select(User, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == actor.organization_id, User.id == user_id)
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user, membership = row
    if payload.role is not None:
        membership.role = payload.role
    if payload.status is not None:
        membership.status = payload.status
    db.commit()
    return DirectoryUserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        time_zone=user.time_zone,
        role=membership.role,
        status=membership.status,
    )
