# NextPhase Compliance Training

Monorepo MVP for the AI-native compliance training platform described in the spec.

## What is included

- `apps/api`
  - FastAPI backend
  - PostgreSQL via SQLAlchemy
  - Demo org, users, course, assignment, quiz state, and analytics seed
  - Firecrawl-powered research collection, AI training generation, deterministic quiz scoring
- `apps/web`
  - Next.js 16 App Router frontend
  - Admin flows for training creation, review, publishing, assignments, and analytics
  - Employee flows for assigned training, watch-gate progress, quiz attempts, and results

## Demo personas

- `admin@acme.test`
- `owner@acme.test`
- `manager@acme.test`
- `employee@acme.test`

The web app exposes a persona switcher in the header. The API also accepts the active persona through `X-User-Email`.

## Run locally

The root `.env` must contain:

- `DATABASE_URL`
- `OPENAI_API_KEY`

Start the API:

```bash
cd /Users/danhpham/Desktop/NextPhase/ComplianceTraining/apps/api
uv sync
uv run uvicorn app.main:app --reload
```

Start the web app in another terminal:

```bash
cd /Users/danhpham/Desktop/NextPhase/ComplianceTraining/apps/web
npm install
npm run dev
```

Open:

- Web: `http://localhost:3000`
- API docs: `http://127.0.0.1:8000/docs`

## Verified

- `uv run pytest`
- `npm run lint`
- `npm run build`
- Live HTTP smoke checks against the running API:
  - `/healthz`
  - `/api/v1/auth/me`
  - `/api/v1/analytics/overview`
  - `/api/v1/me/assignments`
  - `/api/v1/me/assignments/:id`
  - `/api/v1/me/assignments/:id/quiz/start`

## Known MVP shortcuts

- Authentication is demo-header based rather than production auth.
- Video progress UI saves watch progress from the native embedded lesson player.
- Database schema is created on startup for the MVP seed path rather than through a finished Alembic workflow.
