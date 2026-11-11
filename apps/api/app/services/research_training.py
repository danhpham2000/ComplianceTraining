import json
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from textwrap import shorten
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.ai.client import generate_research_brief, generate_assessment
from app.core.config import ROOT_DIR, get_settings


SEARCH_ENDPOINT = "https://api.firecrawl.dev/v2/search"
GENERATED_ROOT = ROOT_DIR / "apps/web/public/generated/trainings"
LOGO_PATH = ROOT_DIR / "apps/web/public/nextphase-logo.png"
VIDEO_SIZE = (1280, 720)
PRIMARY = "#f38820"
PRIMARY_SOFT = "#fff4e8"
INK = "#16181d"
MUTED = "#6f819c"
BORDER = "#eadfd1"


@dataclass
class GeneratedTrainingPackage:
    description: str
    transcript_text: str
    transcript_segments: list[dict]
    learning_objectives: list[str]
    questions: list
    video_url: str
    thumbnail_url: str
    duration_seconds: int
    source_title: str
    source_references: list[dict]


def build_research_training(
    *,
    training_id: str,
    title: str,
    research_query: str,
    question_count: int,
) -> GeneratedTrainingPackage:
    results = _search_sources(research_query)
    source_context = _build_source_context(results)
    brief = generate_research_brief(
        title=title,
        research_query=research_query,
        source_context=source_context,
    )
    render_result = _render_training_video(
        training_id=training_id,
        title=title,
        brief=brief,
    )
    assessment = generate_assessment(
        title=title,
        transcript_text=render_result["transcript_text"],
        transcript_segments=render_result["segments"],
        admin_instructions=(
            "Use only the lesson narration and citations. Keep every question tightly aligned to the generated lesson."
        ),
        question_count=question_count,
    )
    return GeneratedTrainingPackage(
        description=brief.description,
        transcript_text=render_result["transcript_text"],
        transcript_segments=render_result["segments"],
        learning_objectives=brief.learningObjectives,
        questions=assessment.questions,
        video_url=render_result["video_url"],
        thumbnail_url=render_result["thumbnail_url"],
        duration_seconds=render_result["duration_seconds"],
        source_title=f"{title} lecture lesson",
        source_references=[item.model_dump() for item in brief.references],
    )


def remove_generated_training_assets(source_url: str | None) -> None:
    if not source_url or not source_url.startswith("/generated/trainings/"):
        return
    parts = Path(source_url).parts
    if len(parts) < 4:
        return
    target_dir = GENERATED_ROOT / parts[3]
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)


def _search_sources(research_query: str) -> list[dict]:
    settings = get_settings()
    if not settings.firecrawl_api_key:
        raise RuntimeError("FIRECRAWL_API_KEY is not configured")

    queries = [
        f"{research_query} best practices 2026",
        f"{research_query} employee guidance 2026",
        f"{research_query} workplace scenario examples employee training 2026",
    ]
    collected: list[dict] = []
    seen_urls: set[str] = set()
    for query in queries:
        payload = {
            "query": query,
            "limit": 4,
            "sources": ["web"],
            "country": "US",
            "safe": True,
            "timeout": 60000,
            "ignoreInvalidURLs": True,
            "highlights": True,
            "tbs": "qdr:y",
            "scrapeOptions": {
                "formats": [{"type": "markdown"}],
            },
        }
        response = httpx.post(
            SEARCH_ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        if response.status_code == 401:
            raise RuntimeError("Firecrawl rejected the API key. Verify FIRECRAWL_API_KEY in the environment.")
        response.raise_for_status()
        body = response.json()
        data = body.get("data")
        if isinstance(data, dict):
            candidates = data.get("web") or data.get("results") or []
        else:
            candidates = data or body.get("results") or body.get("web") or []
        for item in candidates:
            url = str(item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            markdown = _clean_text(item.get("markdown") or "")
            description = _clean_text(item.get("description") or "")
            highlights = item.get("highlights") or []
            if not markdown and not description and not highlights:
                continue
            seen_urls.add(url)
            collected.append(
                {
                    "title": str(item.get("title") or urlparse(url).netloc),
                    "url": url,
                    "description": description,
                    "markdown": markdown,
                    "highlights": [str(value).strip() for value in highlights if str(value).strip()],
                }
            )

    if not collected:
        raise RuntimeError("Firecrawl did not return usable research results for this topic.")
    return collected[:6]


def _build_source_context(results: list[dict]) -> str:
    blocks: list[str] = []
    for index, item in enumerate(results, start=1):
        excerpt = item["markdown"][:2800] if item["markdown"] else item["description"][:900]
        highlights = "\n".join(f"- {entry}" for entry in item["highlights"][:4])
        blocks.append(
            "\n".join(
                [
                    f"Source {index}",
                    f"Title: {item['title']}",
                    f"URL: {item['url']}",
                    f"Description: {item['description'] or 'N/A'}",
                    f"Highlights:\n{highlights or '- None'}",
                    f"Excerpt:\n{excerpt or 'N/A'}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _render_training_video(*, training_id: str, title: str, brief) -> dict:
    asset_dir = GENERATED_ROOT / training_id
    if asset_dir.exists():
        shutil.rmtree(asset_dir, ignore_errors=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    slides = [
        {
            "heading": title,
            "narration": brief.summary,
            "bullets": brief.learningObjectives[:3],
            "example": brief.sections[0].example if brief.sections else "",
            "sourceUrls": [item.url for item in brief.references[:3]],
        },
        *[
            {
                "heading": section.heading,
                "narration": section.narration,
                "bullets": section.bullets,
                "example": section.example,
                "sourceUrls": section.sourceUrls,
            }
            for section in brief.sections
        ],
    ]

    segments: list[dict] = []
    transcript_parts: list[str] = []
    concat_lines: list[str] = []
    current_second = 0
    thumbnail_path = asset_dir / "thumbnail.png"

    for index, slide in enumerate(slides, start=1):
        image_path = asset_dir / f"slide-{index:02d}.png"
        audio_path = asset_dir / f"audio-{index:02d}.wav"
        chunk_path = asset_dir / f"chunk-{index:02d}.mp4"
        spoken_narration = _build_spoken_narration(slide, is_intro=index == 1)
        _synthesize_speech(spoken_narration, audio_path)
        duration = max(4, round(_probe_duration(audio_path)))
        if index == 1:
            _render_lecture_intro_frame(
                image_path=image_path,
                training_title=title,
                summary=slide["narration"],
                bullets=slide["bullets"],
            )
        else:
            _render_lecture_frame(
                image_path=image_path,
                training_title=title,
                heading=slide["heading"],
                bullets=slide["bullets"],
                example=slide["example"],
            )
        _render_video_chunk(image_path=image_path, audio_path=audio_path, output_path=chunk_path)
        concat_lines.append(f"file '{chunk_path.name}'")
        transcript_parts.append(
            "\n".join(
                [
                    slide["heading"],
                    spoken_narration,
                    f"Example: {slide['example'] or 'N/A'}",
                    f"Sources: {', '.join(slide['sourceUrls']) or 'N/A'}",
                ]
            )
        )
        segments.append(
            {
                "title": slide["heading"],
                "text": spoken_narration,
                "start": current_second,
                "duration": duration,
                "bullets": slide["bullets"],
                "example": slide["example"],
                "citations": slide["sourceUrls"],
            }
        )
        current_second += duration

    if not thumbnail_path.exists():
        shutil.copyfile(asset_dir / "slide-01.png", thumbnail_path)

    concat_file = asset_dir / "concat.txt"
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
    lesson_path = asset_dir / "lesson.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(lesson_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return {
        "video_url": f"/generated/trainings/{training_id}/lesson.mp4",
        "thumbnail_url": f"/generated/trainings/{training_id}/thumbnail.png",
        "duration_seconds": current_second,
        "segments": segments,
        "transcript_text": "\n\n".join(transcript_parts),
    }


def _build_spoken_narration(slide: dict, *, is_intro: bool) -> str:
    narration = str(slide["narration"] or "").strip()
    example = str(slide["example"] or "").strip()
    if is_intro or not example:
        return narration
    return f"{narration} For example, {example}"


def _render_lecture_intro_frame(
    *,
    image_path: Path,
    training_title: str,
    summary: str,
    bullets: list[str],
) -> None:
    image = Image.new("RGB", VIDEO_SIZE, "#f8f5ef")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 10, 720), fill=PRIMARY)
    draw.rounded_rectangle((28, 28, 1252, 692), radius=30, outline="#ded6ca", width=2)
    draw.ellipse((1025, -110, 1430, 260), fill="#ffe1bb")
    draw.ellipse((-160, 572, 184, 870), fill="#fff0df")

    eyebrow_font = _load_font(16, bold=True)
    heading_font = _select_heading_font(training_title, max_width=800, large=68, medium=61, small=54)
    summary_font = _load_font(27)
    step_label_font = _load_font(15, bold=True)
    step_font = _load_font(23, bold=True)

    draw.text((82, 76), "NEXT PHASE TRAINING", fill=PRIMARY, font=eyebrow_font)
    draw.text((1090, 76), "INTRODUCTION", fill="#847c73", font=eyebrow_font)
    heading_bottom = _draw_wrapped_text(
        draw=draw,
        x=82,
        y=128,
        lines=_wrap_text(training_title, heading_font, 800)[:2],
        font=heading_font,
        fill=INK,
        line_height=72,
    )

    summary_top = max(294, heading_bottom + 28)
    _draw_wrapped_text(
        draw=draw,
        x=82,
        y=summary_top,
        lines=_wrap_text(_format_slide_bullet(summary, max_chars=180), summary_font, 770)[:3],
        font=summary_font,
        fill="#6d6a65",
        line_height=38,
    )

    focus_items = bullets[:3] or ["Follow secure data habits."]
    card_y = 530
    for index, bullet in enumerate(focus_items[:3]):
        card_x = 82 + index * 270
        draw.line((card_x, card_y, card_x + 224, card_y), fill=INK, width=2)
        draw.text((card_x, card_y + 18), f"0{index + 1}", fill=PRIMARY, font=step_label_font)
        _draw_wrapped_text(
            draw=draw,
            x=card_x,
            y=card_y + 46,
            lines=_wrap_text(_format_slide_bullet(bullet, max_chars=38), step_font, 224)[:2],
            font=step_font,
            fill=INK,
            line_height=27,
        )

    _paste_logo_bottom_right(image, x=956, y=606)
    image.save(image_path)


def _render_lecture_frame(
    *,
    image_path: Path,
    training_title: str,
    heading: str,
    bullets: list[str],
    example: str,
) -> None:
    image = Image.new("RGB", VIDEO_SIZE, "#f8f5ef")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 10, 720), fill=PRIMARY)
    draw.rounded_rectangle((28, 28, 1252, 692), radius=30, outline="#ded6ca", width=2)
    draw.ellipse((1065, -128, 1430, 212), fill="#ffe1bb")

    eyebrow_font = _load_font(16, bold=True)
    heading_font = _select_heading_font(heading, max_width=820, large=64, medium=58, small=52)
    section_font = _load_font(16, bold=True)
    scenario_font = _load_font(27)
    cue_font = _load_font(21, bold=True)
    action_font = _load_font(27, bold=True)
    takeaway_font = _load_font(21, bold=True)

    draw.text((82, 76), "SCENARIO", fill=PRIMARY, font=eyebrow_font)
    draw.text((1088, 76), "NEXT PHASE", fill="#847c73", font=eyebrow_font)
    heading_bottom = _draw_wrapped_text(
        draw=draw,
        x=82,
        y=126,
        lines=_wrap_text(heading, heading_font, 820)[:2],
        font=heading_font,
        fill=INK,
        line_height=68,
    )

    scene_top = max(286, heading_bottom + 32)
    callout_text = example.strip() or (bullets[0] if bullets else training_title)
    draw.text((82, scene_top - 26), "WORKPLACE SCENARIO", fill="#847c73", font=section_font)
    _draw_wrapped_text(
        draw=draw,
        x=82,
        y=scene_top + 8,
        lines=_wrap_text(_format_slide_bullet(callout_text, max_chars=165), scenario_font, 650)[:4],
        font=scenario_font,
        fill="#353231",
        line_height=37,
    )

    action_top = max(244, scene_top - 12)
    draw.rectangle((836, action_top, 1170, 522), fill=INK)
    draw.text((872, action_top + 38), "RECOMMENDED ACTION", fill="#ffbd7b", font=section_font)
    _draw_wrapped_text(
        draw=draw,
        x=872,
        y=action_top + 94,
        lines=_wrap_text(_format_slide_bullet(bullets[0] if bullets else callout_text, max_chars=115), action_font, 252)[:6],
        font=action_font,
        fill="#ffffff",
        line_height=35,
    )

    cues_top = 472
    draw.line((82, cues_top, 742, cues_top), fill=INK, width=2)
    draw.text((82, cues_top + 20), "DECISION CUES", fill="#847c73", font=section_font)
    for index, bullet in enumerate((bullets[:3] or ["Apply the recommended compliance habit."])[:3]):
        cue_x = 82 + index * 220
        draw.text((cue_x, cues_top + 54), f"0{index + 1}", fill=PRIMARY, font=section_font)
        _draw_wrapped_text(
            draw=draw,
            x=cue_x,
            y=cues_top + 78,
            lines=_wrap_text(_format_slide_bullet(bullet, max_chars=30), cue_font, 190)[:2],
            font=cue_font,
            fill=INK,
            line_height=25,
        )

    takeaway_top = 610
    draw.line((82, takeaway_top, 824, takeaway_top), fill="#ded6ca", width=1)
    draw.text((82, takeaway_top + 18), "TAKEAWAY", fill=PRIMARY, font=section_font)
    _draw_wrapped_text(
        draw=draw,
        x=212,
        y=takeaway_top + 16,
        lines=_wrap_text(_format_slide_bullet(bullets[-1] if bullets else heading, max_chars=64), takeaway_font, 580)[:2],
        font=takeaway_font,
        fill=INK,
        line_height=24,
    )
    _paste_logo_bottom_right(image, x=956, y=606)
    image.save(image_path)


def _load_logo() -> Image.Image | None:
    if not LOGO_PATH.exists():
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo.thumbnail((220, 72))
    return logo


def _paste_logo_bottom_right(image: Image.Image, *, x: int, y: int) -> None:
    logo = _load_logo()
    if logo:
        image.paste(logo, (x, y), logo)


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _select_heading_font(text: str, *, max_width: int, large: int, medium: int, small: int) -> ImageFont.ImageFont:
    for size in (large, medium, small):
        font = _load_font(size, bold=True)
        if len(_wrap_text(text, font, max_width)) <= 2:
            return font
    return _load_font(small, bold=True)


def _format_slide_bullet(text: str, *, max_chars: int) -> str:
    compact = " ".join(text.strip().split())
    compact = re.sub(r"\bcommon\b", "", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bdaily\b", "", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bbefore acting\b", "", compact, flags=re.IGNORECASE)
    compact = " ".join(compact.replace(" ,", ",").split())
    compact = compact.strip(" ,.;:")
    if len(compact) <= max_chars:
        return compact

    fragments = [
        part.strip(" ,.;:")
        for part in re.split(r",|;|:\s+| and | but | while | through ", compact)
        if part.strip(" ,.;:")
    ]
    if fragments:
        candidate = fragments[0]
        for fragment in fragments[1:]:
            joined = f"{candidate}, {fragment}"
            if len(joined) > max_chars:
                break
            candidate = joined
        if candidate and len(candidate) <= max_chars:
            return candidate

    return shorten(compact, width=max_chars, placeholder="...")


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        next_value = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), next_value, font=font)[2]
        if width <= max_width or not current:
            current = next_value
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _draw_wrapped_text(
    *,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    lines: list[str],
    font: ImageFont.ImageFont,
    fill: str,
    line_height: int,
) -> int:
    cursor_y = y
    for line in lines:
        draw.text((x, cursor_y), line, fill=fill, font=font)
        cursor_y += line_height
    return cursor_y


def _synthesize_speech(text: str, audio_path: Path) -> None:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for narrated training videos.")
    try:
        response = httpx.post(
            f"{settings.openrouter_base_url.rstrip('/')}/audio/speech",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.web_app_url,
                "X-OpenRouter-Title": "NextPhase Compliance Training",
            },
            json={
                "model": settings.openrouter_tts_model,
                "input": text,
                "voice": settings.openrouter_tts_voice,
                "response_format": "pcm",
            },
            timeout=180,
        )
        response.raise_for_status()
        with wave.open(str(audio_path), "wb") as audio_file:
            audio_file.setnchannels(1)
            audio_file.setsampwidth(2)
            audio_file.setframerate(24000)
            audio_file.writeframes(response.content)
    except httpx.HTTPError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise RuntimeError(f"OpenRouter text-to-speech failed. {detail}") from exc


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def _render_video_chunk(
    *,
    image_path: Path,
    audio_path: Path,
    output_path: Path,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "stillimage",
    ]
    command.extend(
        [
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    subprocess.run(command, check=True, capture_output=True, text=True)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
