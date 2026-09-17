from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import analytics, assignments, auth, employee, notifications, training
from app.core.config import ROOT_DIR, get_settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.generated_assets import generated_asset_content_type, restore_generated_training_asset


settings = get_settings()
generated_assets_root = ROOT_DIR / "apps/web/public/generated"
generated_assets_root.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(training.router, prefix=settings.api_v1_prefix)
app.include_router(assignments.router, prefix=settings.api_v1_prefix)
app.include_router(employee.router, prefix=settings.api_v1_prefix)
app.include_router(analytics.router, prefix=settings.api_v1_prefix)
app.include_router(notifications.router, prefix=settings.api_v1_prefix)


@app.get("/generated/trainings/{training_id}/{filename}")
def generated_training_asset(training_id: str, filename: str):
    db = SessionLocal()
    try:
        path = restore_generated_training_asset(db, training_id=training_id, filename=filename)
    finally:
        db.close()
    if not path:
        raise HTTPException(status_code=404, detail="Generated asset not found.")
    return FileResponse(
        path,
        media_type=generated_asset_content_type(filename),
        headers={"Cache-Control": "public, max-age=3600"},
    )


app.mount("/generated", StaticFiles(directory=generated_assets_root), name="generated")


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
