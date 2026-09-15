from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.config import ROOT_DIR

PRIMARY = "#f38820"
PRIMARY_SOFT = "#fff1df"
INK = "#1f1a15"
MUTED = "#6f819c"
LINE = "#e9dccd"
ACCENT = "#f6e7d7"


@dataclass
class CertificateContext:
    assignment_id: uuid.UUID
    assignment_recipient_id: uuid.UUID
    organization_name: str
    employee_name: str
    employee_email: str
    assignment_name: str
    training_title: str
    completed_at: datetime
    score: float | None

    @property
    def certificate_number(self) -> str:
        return build_certificate_number(self.assignment_recipient_id, self.completed_at)

    @property
    def filename(self) -> str:
        title_slug = slugify(self.training_title)[:48] or "training-certificate"
        return f"nextphase-certificate-{title_slug}.pdf"


def build_certificate_number(assignment_recipient_id: uuid.UUID, completed_at: datetime) -> str:
    return f"NP-{completed_at.strftime('%Y%m%d')}-{str(assignment_recipient_id).split('-')[0].upper()}"


def slugify(value: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def render_certificate_pdf(context: CertificateContext) -> bytes:
    image = Image.new("RGB", (1600, 1100), "#fffdf9")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((34, 34, 1566, 1066), radius=44, outline=LINE, width=4, fill="#fffdf9")
    draw.ellipse((1130, 70, 1480, 420), fill=PRIMARY_SOFT)
    draw.ellipse((-90, 720, 190, 1000), fill="#fff7ef")
    draw.rounded_rectangle((102, 104, 392, 170), radius=32, fill="#fff6ea")
    draw.rounded_rectangle((100, 846, 1500, 978), radius=28, outline=LINE, width=2, fill="#fffcf8")
    draw.rounded_rectangle((1130, 774, 1440, 1014), radius=155, fill=ACCENT, outline="#efcfaa", width=3)

    label_font = _load_font(22, bold=True)
    heading_font = _select_heading_font(context.training_title, max_width=980, large=76, medium=68, small=60)
    body_font = _load_font(30)
    body_bold_font = _load_font(32, bold=True)
    meta_label_font = _load_font(18, bold=True)
    meta_value_font = _load_font(24)
    seal_font = _load_font(28, bold=True)
    seal_small_font = _load_font(18, bold=True)

    draw.text((132, 120), "TRAINING CERTIFICATE", fill=PRIMARY, font=label_font)
    draw.text((132, 228), "Certificate of Completion", fill=INK, font=_load_font(66, bold=True))
    draw.text((132, 330), "This certifies that", fill=MUTED, font=body_font)
    draw.text((132, 388), context.employee_name, fill=INK, font=_load_font(58, bold=True))
    draw.text((132, 458), context.employee_email, fill=MUTED, font=_load_font(24))
    draw.text((132, 528), "successfully completed the NextPhase compliance training", fill=MUTED, font=body_font)

    title_lines = _wrap_text(context.training_title, heading_font, 960)[:2]
    title_y = 592
    for line in title_lines:
        draw.text((132, title_y), line, fill=INK, font=heading_font)
        title_y += heading_font.size + 12

    draw.text(
        (132, title_y + 24),
        f"Assignment: {context.assignment_name}",
        fill=MUTED,
        font=body_bold_font,
    )

    score_label = f"{context.score:.0f}%" if context.score is not None else "Passed"
    draw.text((1216, 834), "COMPLETED", fill=PRIMARY, font=seal_font)
    draw.text((1220, 876), score_label, fill=INK, font=_load_font(54, bold=True))
    draw.text((1210, 948), "Official score", fill="#9a7b5c", font=seal_small_font)

    metadata = [
        ("Issued", context.completed_at.strftime("%B %d, %Y")),
        ("Certificate no.", context.certificate_number),
        ("Workspace", context.organization_name),
    ]
    meta_x = 132
    for label, value in metadata:
        draw.text((meta_x, 880), label.upper(), fill="#9a7b5c", font=meta_label_font)
        draw.text((meta_x, 915), value, fill=INK, font=meta_value_font)
        meta_x += 330

    draw.text((126, 1014), "Compliance", fill=MUTED, font=_load_font(22, bold=True))
    draw.text((292, 1014), "Issued by NextPhase", fill=MUTED, font=_load_font(22))
    _paste_logo(image, max_width=278, bottom_right=(1436, 1014))

    buffer = BytesIO()
    image.save(buffer, format="PDF", resolution=144.0)
    return buffer.getvalue()


def _paste_logo(image: Image.Image, *, max_width: int, bottom_right: tuple[int, int]) -> None:
    logo_path = ROOT_DIR / "apps/web/public/nextphase-logo.png"
    if not logo_path.exists():
        return

    try:
        logo = Image.open(logo_path).convert("RGBA")
    except OSError:
        return

    width, height = logo.size
    scale = min(1, max_width / width)
    resized = logo.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
    x = bottom_right[0] - resized.width
    y = bottom_right[1] - resized.height
    image.paste(resized, (x, y), resized)


def _font_candidates(*, bold: bool) -> list[Path]:
    if bold:
        return [
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/Helvetica.ttc"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ]
    return [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Helvetica.ttc"),
        Path("/Library/Fonts/Arial.ttf"),
    ]


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    for candidate in _font_candidates(bold=bold):
        if not candidate.exists():
            continue
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _select_heading_font(text: str, *, max_width: int, large: int, medium: int, small: int) -> ImageFont.ImageFont:
    for size in [large, medium, small]:
        font = _load_font(size, bold=True)
        if len(_wrap_text(text, font, max_width)) <= 2:
            return font
    return _load_font(small, bold=True)


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not text:
        return []

    probe = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(probe)
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = word if not current else f"{current} {word}"
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines
