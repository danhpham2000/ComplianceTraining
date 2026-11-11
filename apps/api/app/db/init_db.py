from sqlalchemy import inspect, text

from app.db.session import engine
from app.models import Base


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_auth_columns()
    remove_unused_organization_columns()


def ensure_auth_columns() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    statements: list[str] = []

    if "password_hash" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")
    if "time_zone" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN time_zone VARCHAR(80)")
    if "email_verified" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE")
    if "verification_code_hash" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN verification_code_hash VARCHAR(255)")
    if "verification_code_expires_at" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN verification_code_expires_at TIMESTAMP WITH TIME ZONE")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def remove_unused_organization_columns() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("organizations")}
    with engine.begin() as connection:
        for column_name in ("ai_script_profile_name", "ai_script_markdown"):
            if column_name in columns:
                connection.execute(text(f"ALTER TABLE organizations DROP COLUMN {column_name}"))
