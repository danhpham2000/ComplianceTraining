from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import VideoProgress, VideoWatchInterval


def record_video_progress(
    db: Session,
    *,
    training_session_id,
    content_source_id,
    duration_seconds: int | None,
    start_second: int,
    end_second: int,
    current_position_seconds: int,
) -> VideoProgress:
    progress = db.execute(
        select(VideoProgress).where(
            VideoProgress.training_session_id == training_session_id,
            VideoProgress.content_source_id == content_source_id,
        )
    ).scalar_one_or_none()
    if not progress:
        progress = VideoProgress(
            training_session_id=training_session_id,
            content_source_id=content_source_id,
            furthest_position_seconds=0,
            unique_watched_seconds=0,
            watch_percentage=0,
            last_position_seconds=0,
        )
        db.add(progress)
        db.flush()

    start = max(0, min(start_second, end_second))
    end = max(start, end_second)

    overlapping = db.execute(
        select(VideoWatchInterval).where(
            VideoWatchInterval.video_progress_id == progress.id,
            VideoWatchInterval.end_second >= start - 1,
            VideoWatchInterval.start_second <= end + 1,
        )
    ).scalars().all()

    merged_start = start
    merged_end = end
    for interval in overlapping:
        merged_start = min(merged_start, interval.start_second)
        merged_end = max(merged_end, interval.end_second)
        db.delete(interval)

    db.add(
        VideoWatchInterval(
            video_progress_id=progress.id,
            start_second=merged_start,
            end_second=merged_end,
        )
    )
    db.flush()

    intervals = db.execute(
        select(VideoWatchInterval).where(VideoWatchInterval.video_progress_id == progress.id)
    ).scalars().all()
    unique_watched_seconds = sum(max(0, interval.end_second - interval.start_second) for interval in intervals)

    progress.unique_watched_seconds = unique_watched_seconds
    progress.furthest_position_seconds = max(progress.furthest_position_seconds, end, current_position_seconds)
    progress.last_position_seconds = current_position_seconds
    effective_duration = duration_seconds or max(current_position_seconds, end, progress.furthest_position_seconds, 1)
    progress.watch_percentage = min(100.0, round(unique_watched_seconds / effective_duration * 100, 2))
    progress.updated_at = datetime.now(timezone.utc)
    db.flush()
    return progress
