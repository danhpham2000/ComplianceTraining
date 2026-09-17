from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ROOT_DIR
from app.models import GeneratedAsset


GENERATED_PUBLIC_ROOT = ROOT_DIR / "apps/web/public/generated"
GENERATED_TRAINING_ROOT = GENERATED_PUBLIC_ROOT / "trainings"
ALLOWED_GENERATED_FILENAMES = {
    "lesson.mp4": "video/mp4",
    "thumbnail.png": "image/png",
}


def generated_training_file_path(training_id: str, filename: str) -> Path:
    if filename not in ALLOWED_GENERATED_FILENAMES:
        raise ValueError("Unsupported generated asset filename.")
    return GENERATED_TRAINING_ROOT / str(training_id) / filename


def persist_generated_training_assets(db: Session, *, training_id) -> None:
    for filename, content_type in ALLOWED_GENERATED_FILENAMES.items():
        path = generated_training_file_path(str(training_id), filename)
        if not path.exists():
            continue

        existing = db.execute(
            select(GeneratedAsset)
            .where(GeneratedAsset.course_id == training_id)
            .where(GeneratedAsset.filename == filename)
        ).scalar_one_or_none()
        if existing:
            existing.content_type = content_type
            existing.data = path.read_bytes()
        else:
            db.add(
                GeneratedAsset(
                    course_id=training_id,
                    filename=filename,
                    content_type=content_type,
                    data=path.read_bytes(),
                )
            )


def restore_generated_training_asset(db: Session, *, training_id: str, filename: str) -> Path | None:
    if filename not in ALLOWED_GENERATED_FILENAMES:
        return None

    path = generated_training_file_path(training_id, filename)
    if path.exists():
        return path

    asset = db.execute(
        select(GeneratedAsset)
        .where(GeneratedAsset.course_id == training_id)
        .where(GeneratedAsset.filename == filename)
    ).scalar_one_or_none()
    if not asset:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(asset.data)
    return path


def generated_asset_content_type(filename: str) -> str:
    return ALLOWED_GENERATED_FILENAMES.get(filename, "application/octet-stream")
