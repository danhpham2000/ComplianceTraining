import pytest
from fastapi import HTTPException

from app.services.progress import record_video_progress
from app.services.security import require_allowed_email


def test_placeholder():
    assert callable(record_video_progress)


def test_require_allowed_email_rejects_non_nextphase_domain():
    with pytest.raises(HTTPException) as exc_info:
        require_allowed_email("person@gmail.com")

    assert exc_info.value.status_code == 400
    assert "@nextphase.ai" in exc_info.value.detail


def test_require_allowed_email_allows_nextphase_domain():
    assert require_allowed_email(" Person@NextPhase.AI ") == "person@nextphase.ai"
