import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from textwrap import shorten
from urllib.parse import urlparse

import httpx
from openai import OpenAI
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
CARD = "#fffdfa"
BORDER = "#eadfd1"
PALETTES = [
    ("#fff7ef", "#ffd8b0", "#ffedd5"),
    ("#eef7ff", "#c7e3ff", "#eff6ff"),
    ("#f2fff4", "#c7f1cf", "#ecfdf3"),
    ("#fff2f6", "#ffd0df", "#fff1f5"),
]


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
    generation_mode: str,
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
        generation_mode=generation_mode,
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
        source_title=f"{title} {'cartoon lesson' if generation_mode == 'CARTOON' else 'lecture lesson'}",
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


def _render_training_video(*, training_id: str, title: str, brief, generation_mode: str) -> dict:
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
        audio_path = asset_dir / f"audio-{index:02d}.mp3"
        chunk_path = asset_dir / f"chunk-{index:02d}.mp4"
        _synthesize_speech(slide["narration"], audio_path)
        duration = max(4, round(_probe_duration(audio_path)))
        if generation_mode == "CARTOON":
            source_clip_path = asset_dir / f"sora-{index:02d}.mp4"
            _generate_sora_cartoon_clip(
                output_path=source_clip_path,
                thumbnail_path=thumbnail_path if not thumbnail_path.exists() else None,
                heading=slide["heading"],
                narration=slide["narration"],
                bullets=slide["bullets"],
                example=slide["example"],
                training_title=title,
                scene_index=index - 1,
                duration_seconds=duration,
            )
            _render_video_chunk_from_source(
                source_video_path=source_clip_path,
                audio_path=audio_path,
                output_path=chunk_path,
            )
        else:
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
            _render_video_chunk(
                image_path=image_path,
                audio_path=audio_path,
                output_path=chunk_path,
                animated=False,
            )
        concat_lines.append(f"file '{chunk_path.name}'")
        transcript_parts.append(
            "\n".join(
                [
                    slide["heading"],
                    slide["narration"],
                    f"Example: {slide['example'] or 'N/A'}",
                    f"Sources: {', '.join(slide['sourceUrls']) or 'N/A'}",
                ]
            )
        )
        segments.append(
            {
                "title": slide["heading"],
                "text": slide["narration"],
                "start": current_second,
                "duration": duration,
                "bullets": slide["bullets"],
                "example": slide["example"],
                "citations": slide["sourceUrls"],
            }
        )
        current_second += duration

    if not thumbnail_path.exists():
        fallback_slide = asset_dir / "slide-01.png"
        if fallback_slide.exists():
            shutil.copyfile(fallback_slide, thumbnail_path)
        else:
            _extract_video_thumbnail(asset_dir / "chunk-01.mp4", thumbnail_path)

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


def _render_lecture_intro_frame(
    *,
    image_path: Path,
    training_title: str,
    summary: str,
    bullets: list[str],
) -> None:
    image = Image.new("RGB", VIDEO_SIZE, "#fffaf4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 1256, 696), radius=38, fill="#fffdf9", outline=BORDER, width=2)
    draw.ellipse((944, -46, 1296, 250), fill="#ffe2c5")
    draw.ellipse((-110, 556, 150, 816), fill="#fff0df")
    draw.rounded_rectangle((70, 70, 334, 118), radius=24, fill=PRIMARY_SOFT)
    draw.rounded_rectangle((842, 138, 1164, 470), radius=34, fill="#fff8f0", outline="#f0e4d8", width=2)
    draw.rounded_rectangle((866, 164, 1140, 246), radius=24, fill="#ffffff")
    draw.rounded_rectangle((866, 266, 1140, 334), radius=24, fill="#fff3e4", outline="#f2e1cf", width=2)
    draw.rounded_rectangle((866, 352, 1140, 440), radius=24, fill="#ffffff")
    draw.ellipse((972, 182, 1038, 248), fill=PRIMARY_SOFT)
    draw.ellipse((990, 200, 1022, 232), fill=PRIMARY)
    draw.line((1024, 198, 1062, 164), fill=PRIMARY, width=7)

    heading_font = _select_heading_font(training_title, max_width=692, large=58, medium=52, small=46)
    title_font = _load_font(18, bold=True)
    summary_font = _load_font(22)
    pill_font = _load_font(18, bold=True)
    card_index_font = _load_font(17, bold=True)
    card_body_font = _load_font(16)
    aside_label_font = _load_font(15, bold=True)
    aside_body_font = _load_font(22, bold=True)

    draw.text((92, 84), "INTRODUCTION", fill=PRIMARY, font=pill_font)
    heading_lines = _wrap_text(training_title, heading_font, 692)[:2]
    heading_bottom = _draw_wrapped_text(
        draw=draw,
        x=92,
        y=148,
        lines=heading_lines,
        font=heading_font,
        fill=INK,
        line_height=60,
    )
    draw.text((94, heading_bottom + 18), "Lesson overview", fill="#9a7b5c", font=title_font)
    draw.rounded_rectangle((92, heading_bottom + 52, 776, heading_bottom + 186), radius=28, fill="#f8fbff", outline="#e5ecf5", width=2)

    summary_lines = _wrap_text(shorten(summary, width=180, placeholder="..."), summary_font, 624)
    _draw_wrapped_text(
        draw=draw,
        x=122,
        y=heading_bottom + 82,
        lines=summary_lines[:4],
        font=summary_font,
        fill="#56677f",
        line_height=31,
    )

    objective_cards = bullets[:3] or ["Current guidance synthesized from live research."]
    card_y = 492
    card_width = 232
    card_height = 148
    gap = 16
    for index, bullet in enumerate(objective_cards):
        card_x = 92 + index * (card_width + gap)
        draw.rounded_rectangle((card_x, card_y, card_x + card_width, card_y + card_height), radius=24, fill="#ffffff", outline=BORDER, width=2)
        draw.ellipse((card_x + 18, card_y + 18, card_x + 58, card_y + 58), fill=PRIMARY_SOFT)
        draw.text((card_x + 31, card_y + 29), str(index + 1), fill=PRIMARY, font=card_index_font)
        draw.text((card_x + 74, card_y + 24), "KEY FOCUS", fill="#9f7a4c", font=aside_label_font)
        display_bullet = _format_slide_bullet(bullet, max_chars=52)
        _draw_wrapped_text(
            draw=draw,
            x=card_x + 18,
            y=card_y + 68,
            lines=_wrap_text(display_bullet, card_body_font, card_width - 34)[:4],
            font=card_body_font,
            fill=INK,
            line_height=19,
        )

    draw.text((886, 182), "VISUAL MAP", fill="#9a7b5c", font=aside_label_font)
    draw.text((886, 200), "How this lesson flows", fill=INK, font=aside_body_font)
    intro_steps = [
        ("1", "Recognize warning signs"),
        ("2", "Verify before you act"),
        ("3", "Protect and report fast"),
    ]
    step_y = 270
    for step_number, step_label in intro_steps:
        draw.ellipse((888, step_y + 10, 920, step_y + 42), fill="#ffffff", outline="#f0d6bb", width=2)
        draw.text((900, step_y + 18), step_number, fill=PRIMARY, font=aside_label_font)
        draw.text((938, step_y + 14), step_label, fill=INK, font=_load_font(17, bold=True))
        step_y += 68

    _paste_logo_bottom_right(image, x=952, y=598)
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
    draw.rounded_rectangle((24, 24, 1256, 696), radius=38, fill="#fffdf9", outline=BORDER, width=2)
    draw.rounded_rectangle((72, 72, 336, 118), radius=24, fill=PRIMARY_SOFT)
    draw.ellipse((980, -68, 1298, 202), fill="#ffe6cf")
    draw.rounded_rectangle((830, 132, 1152, 562), radius=34, fill="#fff8f0", outline="#f0e4d8", width=2)
    draw.rounded_rectangle((856, 160, 1126, 288), radius=28, fill="#ffffff")
    draw.ellipse((954, 184, 1026, 256), fill=PRIMARY_SOFT)
    draw.ellipse((975, 205, 1005, 235), fill=PRIMARY)
    draw.line((1008, 202, 1042, 170), fill=PRIMARY, width=7)

    heading_font = _select_heading_font(heading, max_width=646, large=54, medium=48, small=40)
    body_font = _load_font(18, bold=True)
    pill_font = _load_font(18, bold=True)
    bullet_font = _load_font(20)
    panel_title_font = _load_font(16, bold=True)
    panel_body_font = _load_font(17, bold=True)

    draw.text((96, 84), "RESEARCH LESSON", fill=PRIMARY, font=pill_font)
    heading_lines = _wrap_text(heading, heading_font, 646)[:2]
    heading_bottom = _draw_wrapped_text(
        draw=draw,
        x=96,
        y=146,
        lines=heading_lines,
        font=heading_font,
        fill=INK,
        line_height=56,
    )
    draw.text((98, heading_bottom + 16), "Section focus", fill="#9a7b5c", font=body_font)

    content_card_top = heading_bottom + 48
    draw.rounded_rectangle((92, content_card_top, 760, 536), radius=30, fill="#f8fbff", outline="#e5ecf5", width=2)
    draw.text((124, content_card_top + 24), training_title, fill=MUTED, font=_load_font(26))
    draw.text((124, content_card_top + 70), "Key actions", fill="#9a7b5c", font=panel_title_font)

    wrapped_bullets = bullets[:3] or ["Current guidance synthesized from live web research."]
    cursor_y = content_card_top + 106
    for bullet in wrapped_bullets:
        display_bullet = _format_slide_bullet(bullet, max_chars=94)
        draw.ellipse((124, cursor_y + 8, 138, cursor_y + 22), fill=PRIMARY)
        bullet_lines = _wrap_text(display_bullet, bullet_font, 572)[:3]
        _draw_wrapped_text(
            draw=draw,
            x=152,
            y=cursor_y,
            lines=bullet_lines,
            font=bullet_font,
            fill=INK,
            line_height=27,
        )
        cursor_y += len(bullet_lines) * 27 + 14

    if example.strip():
        _draw_example_callout(
            draw=draw,
            x=92,
            y=548,
            width=668,
            title="Example",
            text=example,
        )

    draw.text((878, 326), "WHY IT MATTERS", fill="#9a7b5c", font=panel_title_font)
    panel_lines = _wrap_text(_format_slide_bullet(example or bullets[0], max_chars=82), _load_font(20), 236)[:4]
    _draw_wrapped_text(
        draw=draw,
        x=878,
        y=356,
        lines=panel_lines,
        font=_load_font(20),
        fill=INK,
        line_height=28,
    )
    draw.rounded_rectangle((876, 458, 1106, 488), radius=14, fill="#f6dfc6")
    draw.rounded_rectangle((876, 500, 1042, 520), radius=10, fill="#faecdd")
    draw.rounded_rectangle((876, 530, 1004, 550), radius=10, fill="#faecdd")

    _paste_logo_bottom_right(image, x=962, y=600)
    image.save(image_path)


def _draw_example_callout(
    *,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    title: str,
    text: str,
) -> None:
    height = 114
    draw.rounded_rectangle((x, y, x + width, y + height), radius=28, fill="#fff7ef", outline=BORDER, width=2)
    draw.rounded_rectangle((x + 20, y + 18, x + 132, y + 50), radius=16, fill="#fff0df")
    draw.ellipse((x + 22, y + 62, x + 38, y + 78), fill=PRIMARY)
    label_font = _load_font(15, bold=True)
    body_font = _load_font(18)
    draw.text((x + 38, y + 24), title.upper(), fill=PRIMARY, font=label_font)
    draw.text((x + 48, y + 56), "Scenario", fill="#9a7b5c", font=label_font)
    _draw_wrapped_text(
        draw=draw,
        x=x + 156,
        y=y + 56,
        lines=_wrap_text(_format_slide_bullet(text, max_chars=126), body_font, width - 184)[:2],
        font=body_font,
        fill=INK,
        line_height=24,
    )


def _render_cartoon_frames(
    *,
    frame_dir: Path,
    training_title: str,
    heading: str,
    narration: str,
    bullets: list[str],
    source_urls: list[str],
    scene_index: int,
    duration_seconds: int,
) -> None:
    if frame_dir.exists():
        shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True, exist_ok=True)

    frame_count = max(duration_seconds * 12, 60)
    for frame_index in range(frame_count):
        phase = frame_index / frame_count
        _render_cartoon_frame(
            image_path=frame_dir / f"frame-{frame_index:04d}.png",
            training_title=training_title,
            heading=heading,
            narration=narration,
            bullets=bullets,
            source_urls=source_urls,
            scene_index=scene_index,
            phase=phase,
        )


def _render_cartoon_frame(
    *,
    image_path: Path,
    training_title: str,
    heading: str,
    narration: str,
    bullets: list[str],
    source_urls: list[str],
    scene_index: int,
    phase: float,
) -> None:
    background, accent, panel = PALETTES[scene_index % len(PALETTES)]
    image = Image.new("RGBA", VIDEO_SIZE, background)
    draw = ImageDraw.Draw(image, "RGBA")

    orbit = math.tau * phase
    bob = math.sin(orbit) * 12
    wave = math.sin(orbit * 1.8) * 18

    draw.rounded_rectangle((26, 26, 1254, 694), radius=40, fill=panel, outline=BORDER, width=2)
    draw.ellipse((888, -72, 1280, 240), fill=(*_hex_to_rgb(accent), 105))
    draw.ellipse((-140, 450, 250, 820), fill=(255, 255, 255, 120))
    draw.ellipse((920, 470, 1320, 900), fill=(255, 255, 255, 72))
    _draw_particle_field(draw, phase=phase, accent=accent, scene_index=scene_index)
    _draw_cloud(draw, x=140 + math.sin(orbit * 0.6) * 18, y=98, scale=1.0)
    _draw_cloud(draw, x=930 + math.cos(orbit * 0.7) * 22, y=136, scale=0.82)

    heading_font = _load_font(54, bold=True)
    sub_font = _load_font(27)
    bubble_font = _load_font(26)
    caption_font = _load_font(22)
    source_font = _load_font(18)
    badge_font = _load_font(18, bold=True)

    draw.rounded_rectangle((74, 76, 260, 116), radius=20, fill=(255, 255, 255, 235))
    draw.text((94, 87), "ANIMATED LESSON", fill=PRIMARY, font=badge_font)
    draw.text((88, 150), heading, fill=INK, font=heading_font)
    draw.text((90, 222), shorten(training_title, width=60, placeholder="..."), fill=MUTED, font=sub_font)

    scene_kind = _pick_scene_kind(f"{heading} {' '.join(bullets)} {narration}")
    _draw_cartoon_logo_scene(
        image=image,
        draw=draw,
        x=128,
        y=312 + bob,
        accent=PRIMARY,
        scene_kind=scene_kind,
        background_accent=accent,
        phase=phase,
        wave=wave,
    )

    bubble_text = bullets[:2] or [shorten(narration, width=96, placeholder="...")]
    _draw_speech_bubble(
        draw,
        x=560,
        y=280,
        width=590,
        lines=bubble_text,
        font=bubble_font,
    )

    takeaway = shorten(bullets[0] if bullets else narration, width=118, placeholder="...")
    draw.rounded_rectangle((86, 604, 1196, 660), radius=22, fill=(255, 255, 255, 236))
    draw.text((118, 617), f"Today’s reminder: {takeaway}", fill=INK, font=caption_font)

    sources = ", ".join(_source_labels(source_urls[:3])) or "Live research references"
    draw.text((92, 668), sources, fill=MUTED, font=source_font)
    image.convert("RGB").save(image_path)


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


@lru_cache(maxsize=1)
def _load_logo_mark() -> Image.Image | None:
    if not LOGO_PATH.exists():
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    crop_width = min(int(logo.width * 0.24), 240)
    mark = logo.crop((0, 0, crop_width, logo.height))
    bbox = mark.getbbox()
    if bbox:
        mark = mark.crop(bbox)
    return mark


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
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
    if settings.openai_api_key:
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.audio.speech.create(
                model=settings.openai_tts_model,
                voice=settings.openai_tts_voice,
                input=text,
                response_format="mp3",
            )
            audio_path.write_bytes(response.content)
            return
        except Exception as exc:
            raise RuntimeError(f"OpenAI text-to-speech failed. {exc}") from exc

    subprocess.run(
        ["say", "-o", str(audio_path), text],
        check=True,
        capture_output=True,
        text=True,
    )


def _generate_sora_cartoon_clip(
    *,
    output_path: Path,
    thumbnail_path: Path | None,
    training_title: str,
    heading: str,
    narration: str,
    bullets: list[str],
    example: str,
    scene_index: int,
    duration_seconds: int,
) -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for cartoon video generation with Sora.")

    client = OpenAI(api_key=settings.openai_api_key)
    clip_seconds = _select_sora_duration(duration_seconds)
    prompt = _build_sora_prompt(
        training_title=training_title,
        heading=heading,
        narration=narration,
        bullets=bullets,
        example=example,
        scene_index=scene_index,
        clip_seconds=clip_seconds,
    )

    video = client.videos.create_and_poll(
        model=settings.openai_video_model,
        prompt=prompt,
        seconds=clip_seconds,
        size="1280x720",
        poll_interval_ms=settings.openai_video_poll_interval_ms,
        timeout=1800,
    )
    if video.status != "completed":
        message = getattr(video.error, "message", None) or repr(video.error) or video.status
        raise RuntimeError(f"Sora video generation failed. {message}")

    client.videos.download_content(video.id).write_to_file(output_path)
    if thumbnail_path is not None:
        try:
            client.videos.download_content(video.id, variant="thumbnail").write_to_file(thumbnail_path)
        except Exception:
            _extract_video_thumbnail(output_path, thumbnail_path)


def _select_sora_duration(duration_seconds: int) -> str:
    if duration_seconds <= 6:
        return "4"
    if duration_seconds <= 10:
        return "8"
    return "12"


def _build_sora_prompt(
    *,
    training_title: str,
    heading: str,
    narration: str,
    bullets: list[str],
    example: str,
    scene_index: int,
    clip_seconds: str,
) -> str:
    scene_style = [
        "friendly onboarding explainer set in a modern office",
        "animated employee decision moment with clear cause and effect",
        "cartoon workplace vignette showing safe behavior in action",
        "playful motion-graphics training scene with polished business visuals",
    ][scene_index % 4]
    action_points = "; ".join(_format_slide_bullet(item, max_chars=120) for item in bullets[:3]) or "Show one practical compliance habit."
    example_text = _format_slide_bullet(example, max_chars=140) if example.strip() else "Use a realistic workplace example."
    return "\n".join(
        [
            f"Create a {clip_seconds}-second 2D cartoon compliance training video in 1280x720 landscape.",
            "Visual style: polished animated explainer, smooth motion, expressive characters, soft light backgrounds, orange and cream brand accents, cinematic framing, gentle camera movement.",
            "Do not create a slide deck. Do not show bullet lists, citations, subtitles, UI panels, browser chrome, watermarks, or long on-screen text.",
            f"Lesson title: {training_title}.",
            f"Scene focus: {heading}.",
            f"Teaching goal: {narration}",
            f"Key actions to illustrate: {action_points}",
            f"Example situation: {example_text}",
            f"Scene direction: {scene_style}. Show employees making decisions, consequences, and the safer action path in a clear, kid-friendly but professional tone.",
        ]
    )


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


def _extract_video_thumbnail(source_video_path: Path, thumbnail_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_video_path),
            "-vf",
            "thumbnail,scale=1280:720",
            "-frames:v",
            "1",
            str(thumbnail_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _render_video_chunk(
    *,
    image_path: Path | None,
    audio_path: Path,
    output_path: Path,
    animated: bool,
    frame_pattern: str | None = None,
) -> None:
    command = ["ffmpeg", "-y"]
    if animated and frame_pattern:
        command.extend(["-framerate", "12", "-i", frame_pattern, "-i", str(audio_path)])
        command.extend(["-vf", "fps=24", "-c:v", "libx264", "-preset", "medium"])
    else:
        if image_path is None:
            raise RuntimeError("image_path is required for non-animated video chunks")
        command.extend(["-loop", "1", "-i", str(image_path), "-i", str(audio_path)])
        command.extend(["-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage"])
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


def _render_video_chunk_from_source(
    *,
    source_video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> None:
    source_duration = _probe_duration(source_video_path)
    audio_duration = _probe_duration(audio_path)
    if source_duration <= 0 or audio_duration <= 0:
        raise RuntimeError("Unable to determine source durations for Sora video assembly.")

    speed_factor = audio_duration / source_duration
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            f"setpts={speed_factor:.6f}*PTS,fps=24",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
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
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _source_labels(urls: list[str]) -> list[str]:
    labels: list[str] = []
    for url in urls:
        host = urlparse(url).netloc.replace("www.", "")
        if host:
            labels.append(host)
    return labels


def _pick_scene_kind(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in ["email", "message", "phish", "attachment"]):
        return "email"
    if any(keyword in lowered for keyword in ["password", "login", "credential", "account"]):
        return "lock"
    if any(keyword in lowered for keyword in ["wifi", "network", "public wi-fi", "hotspot", "travel"]):
        return "wifi"
    if any(keyword in lowered for keyword in ["report", "alert", "incident", "notify"]):
        return "alert"
    if any(keyword in lowered for keyword in ["policy", "data", "privacy", "share", "access"]):
        return "clipboard"
    return "shield"


def _draw_cartoon_logo_scene(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    accent: str,
    scene_kind: str,
    background_accent: str,
    phase: float,
    wave: float,
) -> None:
    shadow_y = y + 264
    draw.ellipse((x + 54, shadow_y, x + 380, shadow_y + 50), fill=(50, 60, 80, 42))
    draw.ellipse((x + 36, y + 18, x + 396, y + 332), fill=(255, 255, 255, 90))
    draw.ellipse((x + 86, y + 54, x + 344, y + 284), fill=(255, 255, 255, 138))
    panel_y = y + 36 + math.sin(phase * math.tau * 1.3) * 4
    draw.rounded_rectangle((x + 266, panel_y, x + 388, panel_y + 108), radius=24, fill="#ffffff", outline=BORDER, width=3)
    draw.text((x + 286, panel_y + 18), "FOCUS", fill=MUTED, font=_load_font(16, bold=True))
    _draw_scene_icon(draw, scene_kind=scene_kind, x=x + 294, y=int(panel_y + 34), accent=accent)
    _draw_starburst(draw, x=x + 104, y=y + 34, size=14, fill=PRIMARY_SOFT)
    _draw_starburst(draw, x=x + 360, y=y + 180, size=11, fill=PRIMARY_SOFT)

    _draw_logo_character(image, draw, x=x + 42, y=y + 30, accent=accent, phase=phase, wave=wave)


def _draw_logo_character(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    accent: str,
    phase: float,
    wave: float,
) -> None:
    body = _load_logo_mark()
    if body:
        body = body.copy()
        body.thumbnail((338, 338))
        body_x = int(x + 36)
        body_y = int(y + 58)
        image.paste(body, (body_x, body_y), body)
        body_box = (body_x, body_y, body_x + body.width, body_y + body.height)
    else:
        body_box = (x + 76, y + 82, x + 292, y + 322)
        draw.rounded_rectangle(body_box, radius=48, fill=accent, outline=INK, width=5)

    left, top, right, bottom = body_box
    center_x = (left + right) // 2
    top_y = top - 44
    blink = abs(math.sin(phase * math.tau * 2.0)) < 0.08
    eye_height = 10 if blink else 44

    draw.line([(center_x - 64, top_y - 18), (center_x - 24, top_y - 30)], fill=INK, width=5)
    draw.line([(center_x + 24, top_y - 30), (center_x + 66, top_y - 18)], fill=INK, width=5)
    draw.ellipse((center_x - 88, top_y, center_x - 18, top_y + eye_height + 30), fill="#ffffff", outline=INK, width=4)
    draw.ellipse((center_x + 8, top_y, center_x + 78, top_y + eye_height + 30), fill="#ffffff", outline=INK, width=4)
    pupil_y = top_y + 26
    if not blink:
        pupil_offset = math.sin(phase * math.tau) * 5
        draw.ellipse((center_x - 66 + pupil_offset, pupil_y, center_x - 40 + pupil_offset, pupil_y + 24), fill=INK)
        draw.ellipse((center_x + 28 + pupil_offset, pupil_y, center_x + 54 + pupil_offset, pupil_y + 24), fill=INK)
        draw.ellipse((center_x - 56 + pupil_offset, pupil_y + 7, center_x - 49 + pupil_offset, pupil_y + 14), fill="#ffffff")
        draw.ellipse((center_x + 38 + pupil_offset, pupil_y + 7, center_x + 45 + pupil_offset, pupil_y + 14), fill="#ffffff")

    mouth_y = top + 114
    draw.arc((center_x - 34, mouth_y, center_x + 42, mouth_y + 42), start=10, end=170, fill=INK, width=4)
    draw.ellipse((center_x - 10, mouth_y + 18, center_x + 6, mouth_y + 30), fill=PRIMARY)

    left_arm = [(left + 6, top + 126), (left - 40, top + 184), (left - 20, top + 250)]
    right_arm = [(right - 8, top + 124), (right + 50, top + 72 - wave * 0.4), (right + 84, top + 130 - wave * 0.5)]
    draw.line(left_arm, fill=INK, width=10, joint="curve")
    draw.line(right_arm, fill=INK, width=10, joint="curve")
    _draw_glove(draw, x=left - 30, y=top + 246, waving=False)
    _draw_glove(draw, x=right + 92, y=top + 128 - wave * 0.5, waving=True)

    left_leg_x = left + 92
    right_leg_x = left + 194
    lift = math.sin(phase * math.tau * 1.4) * 8
    draw.line([(left_leg_x, bottom - 18), (left_leg_x - 8, bottom + 74 + lift)], fill=INK, width=10)
    draw.line([(right_leg_x, bottom - 18), (right_leg_x + 10, bottom + 78 - lift)], fill=INK, width=10)
    _draw_shoe(draw, x=left_leg_x - 40, y=bottom + 64 + lift, color="#30d4ff")
    _draw_shoe(draw, x=right_leg_x - 26, y=bottom + 68 - lift, color="#30d4ff")


def _draw_scene_icon(draw: ImageDraw.ImageDraw, *, scene_kind: str, x: int, y: int, accent: str) -> None:
    if scene_kind == "email":
        draw.rounded_rectangle((x, y, x + 78, y + 54), radius=14, outline=accent, width=5)
        draw.line((x + 6, y + 8, x + 39, y + 30, x + 72, y + 8), fill=accent, width=5)
        return
    if scene_kind == "lock":
        draw.rounded_rectangle((x + 10, y + 24, x + 68, y + 74), radius=12, outline=accent, width=5)
        draw.arc((x + 18, y - 2, x + 60, y + 42), start=180, end=360, fill=accent, width=5)
        return
    if scene_kind == "alert":
        draw.ellipse((x + 10, y + 6, x + 68, y + 64), outline=accent, width=5)
        draw.line((x + 39, y + 18, x + 39, y + 42), fill=accent, width=5)
        draw.ellipse((x + 35, y + 48, x + 43, y + 56), fill=accent)
        return
    draw.rounded_rectangle((x + 10, y + 10, x + 68, y + 66), radius=14, outline=accent, width=5)
    draw.line((x + 39, y + 18, x + 39, y + 58), fill=accent, width=5)
    draw.line((x + 24, y + 36, x + 54, y + 36), fill=accent, width=5)


def _draw_glove(draw: ImageDraw.ImageDraw, *, x: float, y: float, waving: bool) -> None:
    draw.ellipse((x - 24, y - 22, x + 24, y + 24), fill="#ffffff", outline=INK, width=3)
    finger_offsets = [(-18, -42), (-4, -48), (10, -44), (22, -30)]
    if waving:
        finger_offsets.append((32, -10))
    for fx, fy in finger_offsets:
        draw.ellipse((x + fx - 8, y + fy - 10, x + fx + 8, y + fy + 12), fill="#ffffff", outline=INK, width=2)


def _draw_shoe(draw: ImageDraw.ImageDraw, *, x: float, y: float, color: str) -> None:
    draw.rounded_rectangle((x, y, x + 74, y + 32), radius=16, fill=color, outline=INK, width=3)


def _draw_particle_field(draw: ImageDraw.ImageDraw, *, phase: float, accent: str, scene_index: int) -> None:
    accent_rgb = _hex_to_rgb(accent)
    for idx in range(16):
        travel = phase * math.tau + (idx * 0.48) + scene_index
        x = 78 + (idx * 71 % 1120) + math.sin(travel * 1.2) * (18 + idx)
        y = 112 + (idx * 43 % 470) + math.cos(travel * 1.4) * (12 + idx * 0.35)
        radius = 4 + (idx % 4) * 3
        alpha = 60 + (idx % 3) * 28
        fill = (*accent_rgb, alpha) if idx % 2 == 0 else (255, 255, 255, 96)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _draw_cloud(draw: ImageDraw.ImageDraw, *, x: float, y: float, scale: float) -> None:
    color = (255, 255, 255, 208)
    circles = [
        (x, y + 12 * scale, 34 * scale),
        (x + 30 * scale, y, 40 * scale),
        (x + 64 * scale, y + 10 * scale, 32 * scale),
        (x + 96 * scale, y + 16 * scale, 24 * scale),
    ]
    for cx, cy, radius in circles:
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
    draw.rounded_rectangle((x - 10 * scale, y + 18 * scale, x + 116 * scale, y + 48 * scale), radius=18, fill=color)


def _draw_starburst(draw: ImageDraw.ImageDraw, *, x: float, y: float, size: float, fill: str) -> None:
    rgb = _hex_to_rgb(fill)
    draw.polygon(
        [
            (x, y - size),
            (x + size * 0.32, y - size * 0.28),
            (x + size, y),
            (x + size * 0.32, y + size * 0.28),
            (x, y + size),
            (x - size * 0.32, y + size * 0.28),
            (x - size, y),
            (x - size * 0.32, y - size * 0.28),
        ],
        fill=(*rgb, 220),
    )


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _draw_speech_bubble(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    lines: list[str],
    font: ImageFont.ImageFont,
) -> None:
    wrapped: list[str] = []
    for line in lines[:2]:
        wrapped.extend(_wrap_text(shorten(line, width=80, placeholder="..."), font, width - 60))
    text_height = max(88, 18 + len(wrapped) * 36)
    draw.rounded_rectangle((x, y, x + width, y + text_height), radius=30, fill="#ffffff", outline=BORDER, width=2)
    draw.polygon([(x + 72, y + text_height), (x + 118, y + text_height), (x + 92, y + text_height + 28)], fill="#ffffff", outline=BORDER)
    cursor_y = y + 22
    for line in wrapped[:4]:
        draw.text((x + 28, cursor_y), line, fill=INK, font=font)
        cursor_y += 34
