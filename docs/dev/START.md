# How to start

## Every time

Open **4 terminals**.

**Terminal 1 — infra (postgres + minio + redis + celery worker)**
```
docker compose up
```

**Terminal 2 — backend**
```
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

**Terminal 3 — frontend**
```
cd frontend
npm run dev
```

**Terminal 4 — Ollama (LLM)**
```
ollama serve
```

App at http://localhost:5173 — API at http://localhost:8000/docs

---

## First time only

```
cp .env.example .env
# edit .env — fill in POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, JWT_SECRET
# generate JWT_SECRET: openssl rand -hex 32

uv sync
cd frontend && npm install
```
