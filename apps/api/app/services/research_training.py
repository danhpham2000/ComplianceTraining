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
    script_profile_name: str | None = None,
    script_markdown: str | None = None,
) -> GeneratedTrainingPackage:
    results = _search_sources(research_query)
    source_context = _build_source_context(results)
    brief = generate_research_brief(
        title=title,
        research_query=research_query,
        source_context=source_context,
        script_profile_name=script_profile_name,
        script_markdown=script_markdown,
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
                source_urls=slide["sourceUrls"],
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
    image = Image.new("RGB", VIDEO_SIZE, "#fffaf4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((34, 34, 1246, 686), radius=42, fill="#fffdf9", outline=BORDER, width=2)
    draw.ellipse((978, -92, 1360, 248), fill="#ffe0bd")
    draw.ellipse((-132, 526, 228, 850), fill="#fff0df")
    draw.rounded_rectangle((82, 74, 308, 118), radius=22, fill=PRIMARY_SOFT)

    badge_font = _load_font(18, bold=True)
    heading_font = _select_heading_font(training_title, max_width=730, large=58, medium=52, small=46)
    summary_font = _load_font(25)
    summary_label_font = _load_font(20, bold=True)
    focus_label_font = _load_font(15, bold=True)
    focus_font = _load_font(19, bold=True)
    step_font = _load_font(23, bold=True)

    draw.text((108, 87), "SCENARIO TRAINING", fill=PRIMARY, font=badge_font)
    heading_bottom = _draw_wrapped_text(
        draw=draw,
        x=82,
        y=148,
        lines=_wrap_text(training_title, heading_font, 730)[:2],
        font=heading_font,
        fill=INK,
        line_height=62,
    )

    summary_top = max(304, heading_bottom + 30)
    draw.text((88, summary_top - 32), "Scenario setup", fill="#9a7b5c", font=summary_label_font)
    draw.rounded_rectangle((82, summary_top, 820, summary_top + 150), radius=30, fill="#f7fbff", outline="#e2ebf4", width=2)
    _draw_wrapped_text(
        draw=draw,
        x=118,
        y=summary_top + 28,
        lines=_wrap_text(_format_slide_bullet(summary, max_chars=130), summary_font, 660)[:3],
        font=summary_font,
        fill="#56677f",
        line_height=34,
    )

    draw.rounded_rectangle((884, 194, 1188, 506), radius=34, fill="#fff8f0", outline="#f0e4d8", width=2)
    draw.text((922, 228), "How to decide", fill="#9a7b5c", font=focus_label_font)
    for index, step in enumerate(["Spot the cue", "Choose action", "Report fast"]):
        y = 278 + index * 70
        draw.ellipse((922, y, 970, y + 48), fill="#ffffff", outline="#f0d6bb", width=2)
        draw.text((939, y + 10), str(index + 1), fill=PRIMARY, font=step_font)
        draw.text((994, y + 8), step, fill=INK, font=step_font)

    focus_items = bullets[:3] or ["Follow secure data habits."]
    card_y = 500
    for index, bullet in enumerate(focus_items[:3]):
        card_x = 82 + index * 272
        draw.rounded_rectangle((card_x, card_y, card_x + 248, card_y + 86), radius=24, fill="#ffffff", outline=BORDER, width=2)
        draw.text((card_x + 22, card_y + 16), f"0{index + 1}", fill=PRIMARY, font=focus_label_font)
        _draw_wrapped_text(
            draw=draw,
            x=card_x + 24,
            y=card_y + 42,
            lines=_wrap_text(_format_slide_bullet(bullet, max_chars=38), focus_font, 198)[:2],
            font=focus_font,
            fill=INK,
            line_height=23,
        )

    _paste_logo_bottom_right(image, x=966, y=586)
    image.save(image_path)


def _render_lecture_frame(
    *,
    image_path: Path,
    training_title: str,
    heading: str,
    bullets: list[str],
    example: str,
    source_urls: list[str],
) -> None:
    image = Image.new("RGB", VIDEO_SIZE, "#fffaf4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((34, 34, 1246, 686), radius=42, fill="#fffdf9", outline=BORDER, width=2)
    draw.ellipse((1000, -70, 1322, 210), fill="#ffe6cf")
    draw.rounded_rectangle((82, 72, 314, 118), radius=23, fill=PRIMARY_SOFT)

    badge_font = _load_font(18, bold=True)
    heading_font = _select_heading_font(heading, max_width=810, large=56, medium=50, small=44)
    section_font = _load_font(20, bold=True)
    bullet_font = _load_font(24, bold=True)
    example_font = _load_font(22)
    small_font = _load_font(16, bold=True)

    draw.text((108, 86), "SCENARIO", fill=PRIMARY, font=badge_font)
    heading_bottom = _draw_wrapped_text(
        draw=draw,
        x=82,
        y=146,
        lines=_wrap_text(heading, heading_font, 810)[:2],
        font=heading_font,
        fill=INK,
        line_height=60,
    )

    scene_top = max(284, heading_bottom + 30)
    callout_text = example.strip() or (bullets[0] if bullets else training_title)
    draw.text((88, scene_top - 32), "Workplace scenario", fill="#9a7b5c", font=section_font)
    draw.rounded_rectangle((82, scene_top, 826, scene_top + 168), radius=32, fill="#f7fbff", outline="#e2ebf4", width=2)
    _draw_wrapped_text(
        draw=draw,
        x=120,
        y=scene_top + 30,
        lines=_wrap_text(_format_slide_bullet(callout_text, max_chars=150), example_font, 650)[:4],
        font=example_font,
        fill="#56677f",
        line_height=30,
    )

    actions_top = scene_top + 198
    draw.text((88, actions_top - 26), "Decision cues", fill="#9a7b5c", font=section_font)
    draw.rounded_rectangle((82, actions_top, 826, actions_top + 96), radius=28, fill="#ffffff", outline=BORDER, width=2)
    cursor_x = 118
    for index, bullet in enumerate((bullets[:3] or ["Apply the recommended compliance habit."])[:3]):
        pill_width = 214
        draw.rounded_rectangle((cursor_x, actions_top + 22, cursor_x + pill_width, actions_top + 72), radius=22, fill="#fff7ef", outline="#f0e0cf", width=1)
        draw.text((cursor_x + 18, actions_top + 36), f"0{index + 1}", fill=PRIMARY, font=small_font)
        _draw_wrapped_text(
            draw=draw,
            x=cursor_x + 52,
            y=actions_top + 31,
            lines=_wrap_text(_format_slide_bullet(bullet, max_chars=32), bullet_font, 144)[:1],
            font=bullet_font,
            fill=INK,
            line_height=26,
        )
        cursor_x += pill_width + 22

    draw.rounded_rectangle((878, 218, 1186, 526), radius=34, fill="#fff8f0", outline="#f0e4d8", width=2)
    draw.rounded_rectangle((910, 252, 1070, 296), radius=22, fill="#ffffff")
    draw.text((936, 265), "CHOICE", fill=PRIMARY, font=small_font)
    _draw_wrapped_text(
        draw=draw,
        x=916,
        y=330,
        lines=_wrap_text(_format_slide_bullet(bullets[0] if bullets else callout_text, max_chars=100), example_font, 232)[:5],
        font=example_font,
        fill=INK,
        line_height=30,
    )

    draw.rounded_rectangle((82, 548, 826, 612), radius=24, fill="#fff7ef", outline="#f0e0cf", width=2)
    draw.text((112, 570), "Takeaway:", fill=PRIMARY, font=section_font)
    draw.text((242, 570), _format_slide_bullet(bullets[-1] if bullets else heading, max_chars=50), fill=INK, font=section_font)
    _paste_logo_bottom_right(image, x=966, y=586)
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
