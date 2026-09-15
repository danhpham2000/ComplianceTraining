from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.client import generate_performance_summary
from app.models import (
    Assignment,
    AssignmentRecipient,
    ContentSource,
    Question,
    QuestionAttempt,
    QuestionOption,
    QuizSession,
    TrainingSession,
    TrainingSummary,
    VideoProgress,
)
from app.schemas.common import OptionEmployeeOut, QuestionEmployeeOut


def get_or_create_training_session(db: Session, recipient: AssignmentRecipient) -> TrainingSession:
    session = db.execute(
        select(TrainingSession).where(TrainingSession.assignment_recipient_id == recipient.id)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not session:
        session = TrainingSession(
            assignment_recipient_id=recipient.id,
            started_at=now,
            last_activity_at=now,
        )
        db.add(session)
        if recipient.status == "NOT_STARTED":
            recipient.status = "IN_PROGRESS"
            recipient.started_at = now
        db.flush()
    return session


def _load_progress(db: Session, training_session_id, content_source_id):
    return db.execute(
        select(VideoProgress).where(
            VideoProgress.training_session_id == training_session_id,
            VideoProgress.content_source_id == content_source_id,
        )
    ).scalar_one_or_none()


def ensure_quiz_unlocked(db: Session, assignment: Assignment, training_session: TrainingSession, content_source: ContentSource) -> None:
    progress = _load_progress(db, training_session.id, content_source.id)
    watch_percentage = progress.watch_percentage if progress else 0
    if watch_percentage < assignment.required_watch_percentage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz is locked until the watch threshold is reached",
        )


def start_quiz(
    db: Session,
    *,
    assignment: Assignment,
    recipient: AssignmentRecipient,
    training_session: TrainingSession,
    content_source: ContentSource,
) -> tuple[QuizSession, list[QuestionEmployeeOut]]:
    ensure_quiz_unlocked(db, assignment, training_session, content_source)
    quiz_session = db.execute(
        select(QuizSession)
        .where(QuizSession.training_session_id == training_session.id)
        .options(selectinload(QuizSession.attempts))
    ).scalar_one_or_none()
    if not quiz_session:
        quiz_session = QuizSession(
            training_session_id=training_session.id,
            started_at=datetime.now(timezone.utc),
            status="IN_PROGRESS",
        )
        db.add(quiz_session)
        db.flush()

    questions = db.execute(
        select(Question)
        .where(Question.training_version_id == assignment.training_version_id)
        .options(selectinload(Question.options))
        .order_by(Question.sort_order)
    ).scalars().all()
    return quiz_session, build_employee_questions(questions, quiz_session.attempts, assignment.max_attempts_per_question)


def build_employee_questions(questions: list[Question], attempts: list[QuestionAttempt], max_attempts: int) -> list[QuestionEmployeeOut]:
    by_question: dict = defaultdict(list)
    for attempt in attempts:
        by_question[attempt.question_id].append(attempt)

    payload: list[QuestionEmployeeOut] = []
    for question in questions:
        existing = sorted(by_question.get(question.id, []), key=lambda item: item.attempt_number)
        terminal = bool(existing and (existing[-1].is_correct or existing[-1].attempt_number >= max_attempts))
        attempts_used = len(existing)
        payload.append(
            QuestionEmployeeOut(
                id=question.id,
                text=question.text,
                type=question.type,
                topic=question.topic,
                hint=None,
                sort_order=question.sort_order,
                options=[OptionEmployeeOut.model_validate(option) for option in question.options],
                attempts_used=attempts_used,
                attempts_remaining=max(0, max_attempts - attempts_used),
                terminal=terminal,
            )
        )
    return payload


def submit_attempt(
    db: Session,
    *,
    assignment: Assignment,
    quiz_session: QuizSession,
    question: Question,
    option: QuestionOption,
    idempotency_key: str,
):
    existing = db.execute(
        select(QuestionAttempt).where(
            QuestionAttempt.quiz_session_id == quiz_session.id,
            QuestionAttempt.client_request_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing:
        correct_option = next(item for item in question.options if item.is_correct)
        return build_attempt_response(existing, assignment.max_attempts_per_question, question, correct_option.id)

    attempts = db.execute(
        select(QuestionAttempt)
        .where(
            QuestionAttempt.quiz_session_id == quiz_session.id,
            QuestionAttempt.question_id == question.id,
        )
        .order_by(QuestionAttempt.attempt_number)
    ).scalars().all()
    if attempts and (attempts[-1].is_correct or attempts[-1].attempt_number >= assignment.max_attempts_per_question):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question is already complete")
    if len(attempts) >= assignment.max_attempts_per_question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attempts exhausted")

    correct_option = next(item for item in question.options if item.is_correct)
    attempt = QuestionAttempt(
        quiz_session_id=quiz_session.id,
        question_id=question.id,
        question_option_id=option.id,
        attempt_number=len(attempts) + 1,
        is_correct=option.id == correct_option.id,
        client_request_key=idempotency_key,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.flush()
    return build_attempt_response(attempt, assignment.max_attempts_per_question, question, correct_option.id)


def build_attempt_response(attempt: QuestionAttempt, max_attempts: int, question: Question, correct_option_id):
    terminal = attempt.is_correct or attempt.attempt_number >= max_attempts
    message = None
    if attempt.is_correct:
        message = "Correct answer."
    elif terminal:
        message = "Please review the video again."
    else:
        message = "Incorrect. Try again."
    return {
        "correct": attempt.is_correct,
        "attempt_number": attempt.attempt_number,
        "attempts_remaining": max(0, max_attempts - attempt.attempt_number),
        "terminal": terminal,
        "message": message,
        "hint": None,
        "explanation": None,
        "correct_option_id": correct_option_id if terminal and not attempt.is_correct else None,
    }


def finalize_quiz(
    db: Session,
    *,
    assignment: Assignment,
    recipient: AssignmentRecipient,
    training_session: TrainingSession,
    quiz_session: QuizSession,
    questions: list[Question],
    content_source: ContentSource,
) -> dict:
    attempts = db.execute(
        select(QuestionAttempt)
        .where(QuestionAttempt.quiz_session_id == quiz_session.id)
        .order_by(QuestionAttempt.question_id, QuestionAttempt.attempt_number)
    ).scalars().all()
    by_question: dict = defaultdict(list)
    for attempt in attempts:
        by_question[attempt.question_id].append(attempt)

    total_questions = len(questions)
    if total_questions == 0:
        raise HTTPException(status_code=400, detail="No questions available")

    terminal_count = 0
    first_attempt_correct = 0
    final_correct = 0
    for question in questions:
        question_attempts = by_question.get(question.id, [])
        if question_attempts:
            first = question_attempts[0]
            last = question_attempts[-1]
            if first.is_correct:
                first_attempt_correct += 1
            if last.is_correct:
                final_correct += 1
            if last.is_correct or last.attempt_number >= assignment.max_attempts_per_question:
                terminal_count += 1
    if terminal_count != total_questions:
        raise HTTPException(status_code=400, detail="All questions must reach a terminal state before completion")

    first_attempt_accuracy = round(first_attempt_correct / total_questions * 100, 2)
    final_accuracy = round(final_correct / total_questions * 100, 2)
    score = final_accuracy

    progress = _load_progress(db, training_session.id, content_source.id)
    watch_percentage = progress.watch_percentage if progress else 0
    passed = score >= assignment.passing_score and watch_percentage >= assignment.required_watch_percentage
    now = datetime.now(timezone.utc)

    quiz_session.completed_at = now
    quiz_session.status = "COMPLETED" if passed else "FAILED"
    quiz_session.score = score
    quiz_session.first_attempt_accuracy = first_attempt_accuracy
    quiz_session.final_accuracy = final_accuracy

    recipient.status = "COMPLETED" if passed else "FAILED"
    recipient.completed_at = now if passed else None
    recipient.final_score = score
    recipient.first_attempt_accuracy = first_attempt_accuracy
    recipient.final_accuracy = final_accuracy

    training_session.completed_at = now if passed else None

    summary_payload = {
        "official_score": score,
        "first_attempt_accuracy": first_attempt_accuracy,
        "final_accuracy": final_accuracy,
        "question_topics": [question.topic for question in questions],
    }
    try:
        summary, provider, model, generated_at = generate_performance_summary(payload=summary_payload)
        db.add(
            TrainingSummary(
                quiz_session_id=quiz_session.id,
                strengths_json=summary.strengths,
                needs_improvement_json=summary.needsImprovement,
                recommended_review_json=summary.recommendedReview,
                summary_text=summary.summary,
                provider=provider,
                model=model,
                generated_at=generated_at,
            )
        )
    except Exception:
        pass

    db.flush()
    return {
        "status": recipient.status,
        "completed_at": recipient.completed_at,
        "official_score": score,
        "passing_score": assignment.passing_score,
        "first_attempt_accuracy": first_attempt_accuracy,
        "final_accuracy": final_accuracy,
        "video_completion_percentage": watch_percentage,
    }
