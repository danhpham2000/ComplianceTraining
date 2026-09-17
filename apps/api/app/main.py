from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import analytics, assignments, auth, employee, notifications, training
from app.core.config import ROOT_DIR, get_settings
from app.db.init_db import init_db


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
app.mount("/generated", StaticFiles(directory=generated_assets_root), name="generated")


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
