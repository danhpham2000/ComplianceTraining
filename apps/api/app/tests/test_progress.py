from types import SimpleNamespace
import wave

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from app.ai import client as ai_client
from app.api.routes.auth import register
from app.api.routes import notifications as notification_routes
from app.core.config import Settings
from app.schemas.auth import RegisterRequest
from app.services.progress import record_video_progress
from app.services import research_training
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


def test_register_requires_an_invitation():
    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class EmptyDatabase:
        def execute(self, statement):
            return EmptyResult()

        def add(self, value):
            pass

        def flush(self):
            pass

    with pytest.raises(HTTPException) as exc_info:
        register(
            RegisterRequest(name="Uninvited User", email="uninvited@nextphase.ai", password="password123"),
            EmptyDatabase(),
        )

    assert exc_info.value.status_code == 403


def test_openrouter_structured_generation_uses_json_schema(monkeypatch):
    class Output(BaseModel):
        title: str

    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"title":"Training"}'}}]}

    settings = SimpleNamespace(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.example/api/v1",
        openrouter_model="test/model",
        web_app_url="https://app.example",
    )
    monkeypatch.setattr(ai_client, "get_settings", lambda: settings)
    monkeypatch.setattr(
        ai_client.httpx,
        "post",
        lambda url, **kwargs: captured.update(url=url, **kwargs) or Response(),
    )

    result = ai_client._parse_structured_response(prompt="Return JSON", text_format=Output)

    assert result == Output(title="Training")
    assert captured["url"] == "https://openrouter.example/api/v1/chat/completions"
    assert captured["json"]["max_tokens"] == 4096
    assert captured["json"]["response_format"]["type"] == "json_schema"


def test_openrouter_retries_an_empty_structured_response(monkeypatch):
    class Output(BaseModel):
        title: str

    class Response:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": self.content}}]}

    responses = iter([Response(None), Response('{"title":"Training"}')])
    settings = SimpleNamespace(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.example/api/v1",
        openrouter_model="test/model",
        web_app_url="https://app.example",
    )
    monkeypatch.setattr(ai_client, "get_settings", lambda: settings)
    monkeypatch.setattr(ai_client.httpx, "post", lambda *args, **kwargs: next(responses))

    result = ai_client._parse_structured_response(prompt="Return JSON", text_format=Output)

    assert result == Output(title="Training")


def test_research_brief_requests_a_three_to_five_minute_spoken_script(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        ai_client,
        "_parse_structured_response",
        lambda **kwargs: captured.update(kwargs) or ai_client.AIResearchBrief(
            summary="Opening summary",
            description="Description",
            learningObjectives=["One", "Two", "Three"],
            sections=[],
            references=[],
        ),
    )

    ai_client.generate_research_brief(
        title="Data security",
        research_query="Data security for employees",
        source_context="Source material",
    )

    prompt = captured["prompt"]
    assert "Produce exactly 5 sections." in prompt
    assert "55 to 70 spoken words" in prompt
    assert "90 to 110 spoken words" in prompt


def test_openrouter_tts_writes_wav(monkeypatch, tmp_path):
    captured = {}

    class Response:
        content = b"\x00\x00\x01\x00"

        def raise_for_status(self):
            pass

    settings = SimpleNamespace(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.example/api/v1",
        openrouter_tts_model="google/gemini-3.8-flash-tts",
        openrouter_tts_voice="Kore",
        web_app_url="https://app.example",
    )
    monkeypatch.setattr(research_training, "get_settings", lambda: settings)
    monkeypatch.setattr(
        research_training.httpx,
        "post",
        lambda url, **kwargs: captured.update(url=url, **kwargs) or Response(),
    )
    output = tmp_path / "narration.wav"

    research_training._synthesize_speech("Narration", output)

    with wave.open(str(output), "rb") as audio_file:
        assert audio_file.getframerate() == 24000
        assert audio_file.readframes(2) == b"\x00\x00\x01\x00"
    assert captured["url"] == "https://openrouter.example/api/v1/audio/speech"
    assert captured["json"]["model"] == "google/gemini-3.8-flash-tts"
    assert captured["json"]["response_format"] == "pcm"


def test_default_cors_allows_the_local_frontend_ports():
    origins = Settings(database_url="postgresql://example").cors_origins

    assert "http://localhost:3000" in origins
    assert "http://localhost:3001" in origins


def test_clear_notifications_only_targets_the_current_actor(monkeypatch):
    captured = {}
    actor = SimpleNamespace(organization_id="organization-id", user=SimpleNamespace(id="user-id"))
    database = SimpleNamespace(commit=lambda: captured.setdefault("committed", True))

    monkeypatch.setattr(
        notification_routes,
        "clear_notifications",
        lambda db, **kwargs: captured.update(db=db, **kwargs) or 3,
    )

    response = notification_routes.delete_notifications(database, actor)

    assert response.message == "Cleared 3 notification(s)."
    assert captured["organization_id"] == "organization-id"
    assert captured["user_id"] == "user-id"
    assert captured["committed"]
