from datetime import datetime
import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


settings = get_settings()
RESEND_API_URL = "https://api.resend.com/emails"


def _send_email(*, to: list[str], subject: str, html: str, text: str, fail_silently: bool) -> str | None:
    if not settings.email_delivery_enabled or not settings.resend_api_key:
        return None

    payload = {
        "from": settings.resend_from_email,
        "to": to,
        "subject": subject,
        "html": html,
        "text": text,
    }

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
        "User-Agent": "nextphase-compliance-training/1.0",
    }

    with httpx.Client(timeout=15.0) as client:
        response = client.post(RESEND_API_URL, headers=headers, json=payload)

    if response.status_code < 400:
        return None

    detail = "Email could not be sent."
    try:
        error_payload = response.json()
    except ValueError:
        error_payload = None
    if isinstance(error_payload, dict):
        message = error_payload.get("message")
        if isinstance(message, str) and message:
            detail = f"Email could not be sent. {message}"

    if fail_silently:
        return detail

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
    )


def send_verification_email(
    email: str,
    code: str,
    expires_at: datetime,
    *,
    fail_silently: bool | None = None,
) -> str | None:
    if not settings.email_delivery_enabled or not settings.resend_api_key:
        return

    if fail_silently is None:
        fail_silently = settings.app_env != "production"

    formatted_expiry = expires_at.strftime("%I:%M %p UTC").lstrip("0")
    html = f"""
    <div style="font-family: Inter, Arial, sans-serif; background:#fff8f2; color:#24201c; padding:32px;">
      <div style="max-width:520px; margin:0 auto; background:#ffffff; border:1px solid rgba(36,32,28,0.12); border-radius:24px; padding:32px;">
        <p style="margin:0 0 12px; font-size:12px; letter-spacing:0.18em; text-transform:uppercase; color:#756a5d;">NextPhase verification</p>
        <h1 style="margin:0 0 12px; font-size:32px; line-height:1.05;">Confirm your email</h1>
        <p style="margin:0 0 24px; font-size:15px; line-height:1.7; color:#756a5d;">
          Use the code below to finish signing in to NextPhase Compliance Training.
        </p>
        <div style="margin:0 0 24px; padding:18px 20px; border-radius:18px; background:#fff0df; border:1px solid rgba(243,136,32,0.18);">
          <span style="font-size:30px; font-weight:700; letter-spacing:0.32em; color:#9a5514;">{code}</span>
        </div>
        <p style="margin:0; font-size:14px; line-height:1.7; color:#756a5d;">
          This code expires at {formatted_expiry}.
        </p>
      </div>
    </div>
    """.strip()

    return _send_email(
        to=[email],
        subject="Verify your NextPhase account",
        html=html,
        text=f"Your NextPhase verification code is {code}. It expires at {formatted_expiry}.",
        fail_silently=fail_silently,
    )


def send_assignment_email(
    *,
    email: str,
    recipient_name: str | None,
    assignment_name: str,
    training_title: str,
    due_at: str | None,
    action_url: str,
) -> str | None:
    salutation = recipient_name or email
    due_line = f"Due date: {due_at}" if due_at else "Due date: not set"
    html = f"""
    <div style="font-family: Inter, Arial, sans-serif; background:#fff8f2; color:#24201c; padding:32px;">
      <div style="max-width:560px; margin:0 auto; background:#ffffff; border:1px solid rgba(36,32,28,0.12); border-radius:24px; padding:32px;">
        <p style="margin:0 0 12px; font-size:12px; letter-spacing:0.18em; text-transform:uppercase; color:#756a5d;">New assignment</p>
        <h1 style="margin:0 0 12px; font-size:30px; line-height:1.08;">{assignment_name}</h1>
        <p style="margin:0 0 16px; font-size:15px; line-height:1.7; color:#756a5d;">{salutation}, you have been assigned a new training module in NextPhase.</p>
        <div style="border:1px solid rgba(243,136,32,0.18); border-radius:18px; background:#fff5ea; padding:18px 20px;">
          <p style="margin:0 0 8px; font-size:14px;"><strong>Training:</strong> {training_title}</p>
          <p style="margin:0; font-size:14px;"><strong>{due_line}</strong></p>
        </div>
        <div style="margin-top:24px;">
          <a href="{action_url}" style="display:inline-block; background:#f38820; color:#ffffff; text-decoration:none; border-radius:999px; padding:12px 20px; font-size:14px; font-weight:600;">Open training</a>
        </div>
      </div>
    </div>
    """.strip()
    text = f"You have a new NextPhase assignment: {assignment_name}. Training: {training_title}. {due_line} Open training: {action_url}"
    return _send_email(
        to=[email],
        subject=f"New training assignment: {assignment_name}",
        html=html,
        text=text,
        fail_silently=True,
    )


def send_completion_email(
    *,
    email: str,
    admin_name: str | None,
    employee_name: str | None,
    assignment_name: str,
    training_title: str,
    score: float | None,
    action_url: str | None = None,
) -> str | None:
    salutation = admin_name or email
    employee_label = employee_name or "An employee"
    score_line = f"Score: {score:.2f}%" if score is not None else "Score: pending"
    html = f"""
    <div style="font-family: Inter, Arial, sans-serif; background:#fff8f2; color:#24201c; padding:32px;">
      <div style="max-width:560px; margin:0 auto; background:#ffffff; border:1px solid rgba(36,32,28,0.12); border-radius:24px; padding:32px;">
        <p style="margin:0 0 12px; font-size:12px; letter-spacing:0.18em; text-transform:uppercase; color:#756a5d;">Assignment completed</p>
        <h1 style="margin:0 0 12px; font-size:30px; line-height:1.08;">Employee completed assigned training</h1>
        <p style="margin:0 0 16px; font-size:15px; line-height:1.7; color:#756a5d;">{salutation}, an assigned employee has completed a training item in NextPhase.</p>
        <div style="border:1px solid rgba(243,136,32,0.18); border-radius:18px; background:#fff5ea; padding:18px 20px;">
          <p style="margin:0 0 8px; font-size:14px;"><strong>Employee:</strong> {employee_label}</p>
          <p style="margin:0 0 8px; font-size:14px;"><strong>Assignment:</strong> {assignment_name}</p>
          <p style="margin:0 0 8px; font-size:14px;"><strong>Training:</strong> {training_title}</p>
          <p style="margin:0; font-size:14px;"><strong>{score_line}</strong></p>
        </div>
        {f'<div style="margin-top:24px;"><a href="{action_url}" style="display:inline-block; background:#f38820; color:#ffffff; text-decoration:none; border-radius:999px; padding:12px 20px; font-size:14px; font-weight:600;">Open workspace</a></div>' if action_url else ''}
      </div>
    </div>
    """.strip()
    text = f"Employee completed assigned training. Employee: {employee_label}. Assignment: {assignment_name}. Training: {training_title}. {score_line}"
    if action_url:
        text = f"{text} Open workspace: {action_url}"
    return _send_email(
        to=[email],
        subject=f"Assignment completed: {assignment_name}",
        html=html,
        text=text,
        fail_silently=True,
    )


def send_certificate_email(
    *,
    email: str,
    employee_name: str | None,
    assignment_name: str,
    training_title: str,
    score: float | None,
    action_url: str,
) -> str | None:
    salutation = employee_name or email
    score_line = f"Official score: {score:.2f}%" if score is not None else "Official score: Passed"
    html = f"""
    <div style="font-family: Inter, Arial, sans-serif; background:#fff8f2; color:#24201c; padding:32px;">
      <div style="max-width:560px; margin:0 auto; background:#ffffff; border:1px solid rgba(36,32,28,0.12); border-radius:24px; padding:32px;">
        <p style="margin:0 0 12px; font-size:12px; letter-spacing:0.18em; text-transform:uppercase; color:#756a5d;">Training completed</p>
        <h1 style="margin:0 0 12px; font-size:30px; line-height:1.08;">Your certificate is ready</h1>
        <p style="margin:0 0 16px; font-size:15px; line-height:1.7; color:#756a5d;">Congratulations {salutation}, you completed your assigned training in NextPhase.</p>
        <div style="border:1px solid rgba(243,136,32,0.18); border-radius:18px; background:#fff5ea; padding:18px 20px;">
          <p style="margin:0 0 8px; font-size:14px;"><strong>Assignment:</strong> {assignment_name}</p>
          <p style="margin:0 0 8px; font-size:14px;"><strong>Training:</strong> {training_title}</p>
          <p style="margin:0; font-size:14px;"><strong>{score_line}</strong></p>
        </div>
        <p style="margin:18px 0 0; font-size:14px; line-height:1.7; color:#756a5d;">Open the completion page to view and download your certificate.</p>
        <div style="margin-top:24px;">
          <a href="{action_url}" style="display:inline-block; background:#f38820; color:#ffffff; text-decoration:none; border-radius:999px; padding:12px 20px; font-size:14px; font-weight:600;">Open certificate</a>
        </div>
      </div>
    </div>
    """.strip()
    text = (
        f"Congratulations, you completed your assigned training. Assignment: {assignment_name}. "
        f"Training: {training_title}. {score_line} Open certificate: {action_url}"
    )
    return _send_email(
        to=[email],
        subject=f"Certificate ready: {assignment_name}",
        html=html,
        text=text,
        fail_silently=True,
    )


def send_invitation_email(
    *,
    email: str,
    recipient_name: str | None,
    inviter_name: str | None,
    role: str,
    action_url: str,
    existing_account: bool,
    fail_silently: bool | None = None,
) -> str | None:
    if fail_silently is None:
        fail_silently = settings.app_env != "production"

    salutation = recipient_name or email
    inviter_label = inviter_name or "An administrator"
    action_label = "Accept invitation"
    status_line = (
        "Your workspace access is ready. Continue with the same email address to enter the workspace."
        if existing_account
        else "Finish account setup with the email below. The invitation page opens with your email prefilled."
    )
    query_url = action_url
    html = f"""
    <div style="font-family: Inter, Arial, sans-serif; background:#fff8f2; color:#24201c; padding:32px;">
      <div style="max-width:560px; margin:0 auto; background:#ffffff; border:1px solid rgba(36,32,28,0.12); border-radius:24px; padding:32px;">
        <p style="margin:0 0 12px; font-size:12px; letter-spacing:0.18em; text-transform:uppercase; color:#756a5d;">Workspace invitation</p>
        <h1 style="margin:0 0 12px; font-size:30px; line-height:1.08;">You were invited to NextPhase</h1>
        <p style="margin:0 0 16px; font-size:15px; line-height:1.7; color:#756a5d;">{salutation}, {inviter_label} invited you to join the compliance workspace.</p>
        <div style="border:1px solid rgba(243,136,32,0.18); border-radius:18px; background:#fff5ea; padding:18px 20px;">
          <p style="margin:0 0 8px; font-size:14px;"><strong>Role:</strong> {role}</p>
          <p style="margin:0 0 8px; font-size:14px;"><strong>Email:</strong> {email}</p>
          <p style="margin:0; font-size:14px;">{status_line}</p>
        </div>
        <div style="margin-top:24px;">
          <a href="{query_url}" style="display:inline-block; background:#f38820; color:#ffffff; text-decoration:none; border-radius:999px; padding:12px 20px; font-size:14px; font-weight:600;">{action_label}</a>
        </div>
      </div>
    </div>
    """.strip()
    text = f"You were invited to NextPhase as {role}. {status_line} Continue here: {query_url}"
    return _send_email(
        to=[email],
        subject="You were invited to NextPhase",
        html=html,
        text=text,
        fail_silently=fail_silently,
    )
