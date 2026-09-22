from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings


class AIOption(BaseModel):
    text: str
    isCorrect: bool


class AIQuestion(BaseModel):
    question: str
    type: str = Field(default="MULTIPLE_CHOICE")
    difficulty: str = Field(default="MEDIUM")
    topic: str
    options: list[AIOption]
    hint: str
    explanation: str
    sourceStartSeconds: int | None = None
    sourceEndSeconds: int | None = None


class AIAssessment(BaseModel):
    summary: str
    learningObjectives: list[str]
    topics: list[str]
    questions: list[AIQuestion]


class AIPerformanceSummary(BaseModel):
    strengths: list[str]
    needsImprovement: list[str]
    recommendedReview: list[dict[str, Any]]
    summary: str


class AIResearchSource(BaseModel):
    title: str
    url: str
    summary: str


class AIResearchSection(BaseModel):
    heading: str
    narration: str
    bullets: list[str]
    example: str
    sourceUrls: list[str]


class AIResearchBrief(BaseModel):
    summary: str
    description: str
    learningObjectives: list[str]
    sections: list[AIResearchSection]
    references: list[AIResearchSource]


def _get_text_provider() -> str:
    settings = get_settings()
    if settings.openrouter_api_key:
        return "openrouter"
    if settings.openai_api_key:
        return "openai"
    raise RuntimeError("Neither OPENROUTER_API_KEY nor OPENAI_API_KEY is configured")


def _get_client() -> OpenAI:
    settings = get_settings()
    if settings.openrouter_api_key:
        return OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key)


def _get_text_model() -> str:
    settings = get_settings()
    if settings.openrouter_api_key:
        return settings.openrouter_model
    return settings.openai_model


def _get_text_request_options() -> dict[str, Any]:
    settings = get_settings()
    if settings.openrouter_api_key:
        return {
            "extra_headers": {
                "HTTP-Referer": settings.web_app_url,
                "X-OpenRouter-Title": "NextPhase Compliance Training",
            },
            "extra_body": {
                "provider": {
                    "require_parameters": True,
                }
            },
        }
    return {}


def _parse_structured_response(
    *,
    prompt: str,
    text_format,
    reasoning_effort: str,
):
    settings = get_settings()
    client = _get_client()
    options = _get_text_request_options()
    request: dict[str, Any] = {
        "model": _get_text_model(),
        "input": [{"role": "user", "content": prompt}],
        "text_format": text_format,
        **options,
    }
    if _get_text_provider() == "openai":
        request["reasoning"] = {"effort": reasoning_effort}
    response = client.responses.parse(**request)
    return response.output_parsed


def generate_assessment(
    *,
    title: str,
    transcript_text: str,
    transcript_segments: list[dict[str, Any]] | None = None,
    admin_instructions: str | None,
    question_count: int,
) -> AIAssessment:
    segment_lines: list[str] = []
    for segment in transcript_segments or []:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        title = str(segment.get("title") or "").strip()
        example = str(segment.get("example") or "").strip()
        bullets = [
            str(item).strip()
            for item in (segment.get("bullets") or [])
            if str(item).strip()
        ][:3]
        start = int(float(segment.get("start") or 0))
        duration = int(float(segment.get("duration") or 0))
        end = max(start, start + duration)
        context_lines = [f"[{start}s - {end}s] {title}".strip(), text]
        if example:
            context_lines.append(f"Scenario example: {example}")
        if bullets:
            context_lines.append(f"Key behaviors: {'; '.join(bullets)}")
        segment_lines.append("\n".join(context_lines))

    segment_context = "\n".join(segment_lines[:220]) if segment_lines else transcript_text
    prompt = f"""
You are generating compliance training assessment content from a source transcript.
The lesson is scenario-based: employees should be tested on what they should do in realistic workplace situations.

Training title: {title}
Question count: {question_count}
Admin instructions: {admin_instructions or "None"}

Requirements:
- Return exactly {question_count} questions.
- Only use facts that are explicitly grounded in the transcript excerpts below.
- Use scenario-based wording for every question unless the transcript cannot support it.
- At least half of the questions must describe a concrete workplace situation and ask for the safest or most compliant employee action.
- For each multiple-choice question, provide exactly 4 options and exactly 1 correct answer.
- Avoid trivia, generic compliance filler, or unsupported claims.
- Include concise hints and explanations.
- Every question must be answerable from one or more transcript excerpts below.
- For every question, set sourceStartSeconds and sourceEndSeconds to the excerpt timestamps that support the answer.
- If the transcript does not support a fact clearly, do not use it.
- Prefer concrete operational behavior, policy actions, scenario examples, warnings, reporting steps, and expected decisions that the speaker actually mentions.
- Distractor options should be plausible employee mistakes from the scenario, not silly or obviously wrong answers.

Transcript excerpts:
{segment_context}
"""
    return _parse_structured_response(
        prompt=prompt,
        text_format=AIAssessment,
        reasoning_effort="low",
    )


def generate_performance_summary(*, payload: dict) -> tuple[AIPerformanceSummary, str, str, datetime]:
    settings = get_settings()
    prompt = f"""
Generate an advisory training summary from this deterministic quiz result payload.
Do not invent HR interpretations or employment recommendations.

Payload:
{payload}
"""
    provider = _get_text_provider()
    model = _get_text_model()
    parsed = _parse_structured_response(
        prompt=prompt,
        text_format=AIPerformanceSummary,
        reasoning_effort="low",
    )
    return parsed, provider, model, datetime.now(timezone.utc)


def generate_research_brief(
    *,
    title: str,
    research_query: str,
    source_context: str,
    script_profile_name: str | None = None,
    script_markdown: str | None = None,
) -> AIResearchBrief:
    current_label = datetime.now(timezone.utc).strftime("%B %d, %Y")
    custom_guide_block = ""
    if script_markdown:
        custom_guide_block = f"""

Additional scripting preference:
- Profile name: {script_profile_name or "Custom workspace guide"}
- Follow the guide below when shaping narration, flow, tone, transitions, and presenter style.
- The guide must never override factual accuracy, source grounding, or compliance constraints.

Custom guide:
{script_markdown[:18000]}
"""
    prompt = f"""
You are building a compliance training lesson from fresh web research.
Your narration should sound like a calm, experienced trainer walking employees through realistic workplace scenarios.

Training title: {title}
Research query: {research_query}

Requirements:
- Use only the source excerpts provided below.
- Prioritize current guidance that is still relevant as of {current_label}.
- Produce 4 to 6 sections.
- Keep narration practical, concise, and suitable for a 3 to 5 minute training video.
- Write for the ear, not the page. Use smooth spoken transitions and natural sentence rhythm.
- The opening summary must do two things:
  1. give the audience a reason to care
  2. introduce the realistic scenario lens employees will use during the lesson
- Each section narration should:
  - revolve around one realistic workplace situation
  - identify the employee context, the risk, the expected behavior, and the consequence of a poor choice
  - use plain language first, then the formal concept only when needed
  - sound natural when spoken aloud
  - add useful context instead of reading bullet points verbatim
  - include a practical employee-facing scenario example
- Avoid generic presentation filler such as "today we are going to talk about" or "in this presentation".
- Avoid marketing language, robotic phrasing, and dense academic prose.
- Every section must cite one or more source URLs from the provided material.
- Do not invent laws, standards, statistics, or company-specific policies.
- Focus on actionable employee behavior, manager expectations, reporting steps, and common failure modes.
- Section headings must be short and slide-friendly, ideally 3 to 7 words.
- Section bullets are for slides only:
  - return 2 or 3 bullets per section
  - each bullet must be a decision cue, warning sign, or expected action
  - prefer short phrases over full sentences
- Every section must include an `example` field:
  - one short, concrete workplace scenario or illustration with an employee, situation, and expected action
  - keep it specific and easy to visualize
  - write it so it can be shown on-screen inside the training video
- The scenario examples must not include real employee names, real secrets, passwords, customer data, or unverifiable company policy.
- Use fictional names and generic business contexts.
- Learning objectives must be concise and concrete.
- The description should be one compact paragraph for the training library.
- Return a references list containing the strongest sources actually used.

Source excerpts:
{source_context}
{custom_guide_block}
"""
    return _parse_structured_response(
        prompt=prompt,
        text_format=AIResearchBrief,
        reasoning_effort="medium",
    )
