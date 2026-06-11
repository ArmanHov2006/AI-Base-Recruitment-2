# SHIP_FIXES — Step-by-Step Fix Guide

Every fix below is self-contained: file path, exact old code, exact new code, why it matters.
Work top-to-bottom — criticals first, then high, then medium.

---

## CRITICAL FIXES — do these before any demo

---

### FIX-1 · `docker-compose.prod.yml` — pgvector image

**File:** `docker-compose.prod.yml`

**Why:** `postgres:16` does not ship the `pgvector` extension. Migration `0020_pgvector_embeddings.py` runs `CREATE EXTENSION IF NOT EXISTS vector` — silently fails on plain postgres, leaving `candidates.embedding` column unusable. Duplicate detection (cosine similarity) and semantic search both break.

**Find:**
```yaml
  postgres:
    image: postgres:16
```

**Replace with:**
```yaml
  postgres:
    image: pgvector/pgvector:pg16
```

---

### FIX-2 · `docker-compose.prod.yml` — add redis service

**File:** `docker-compose.prod.yml`

**Why:** Celery uses Redis as broker. Without it every `apply_pipeline_task.delay(...)` call raises `kombu.exceptions.OperationalError`. All job application uploads get stuck in `parsing` status permanently — the main recruiter workflow is broken.

**Add this block** after the `minio` service (before `ollama`):
```yaml
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
```

Also add `redis_data:` under the `volumes:` section at the bottom.

---

### FIX-3 · `docker-compose.prod.yml` — add Celery worker service

**File:** `docker-compose.prod.yml`

**Why:** Even with Redis running, no worker means tasks queue but never execute. Background jobs that break without a worker:
- `apply_pipeline_task` — parses resume + creates candidate (primary pipeline)
- `score_candidates_for_job_task` — AI scoring
- `_purge_old_audit_logs` — audit log maintenance

**Add this block** after the `backend` service:
```yaml
  worker:
    build: .
    restart: unless-stopped
    command: uv run celery -A app.worker.celery_app worker -l info --concurrency=2
    env_file: .env.prod
    environment:
      POSTGRES_HOST: postgres
      MINIO_INTERNAL_URL: http://minio:9000
      OLLAMA_BASE_URL: http://ollama:11434
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
      redis:
        condition: service_healthy
```

---

### FIX-4 · `docker-compose.prod.yml` — add missing env vars to backend

**File:** `docker-compose.prod.yml`

**Why:** `backend` service env block is missing `MINIO_BUCKET`, `MINIO_INTERNAL_URL`, `REDIS_URL`. Without `MINIO_BUCKET`, `ensure_bucket()` at startup uses undefined bucket name. Without `REDIS_URL`, Celery task dispatch from the API (e.g. `apply_pipeline_task.delay()`) fails.

**Find:**
```yaml
  backend:
    build: .
    restart: unless-stopped
    env_file: .env.prod
    environment:
      POSTGRES_HOST: postgres
      MINIO_INTERNAL_URL: http://minio:9000
      OLLAMA_BASE_URL: http://ollama:11434
```

**Replace with:**
```yaml
  backend:
    build: .
    restart: unless-stopped
    env_file: .env.prod
    environment:
      POSTGRES_HOST: postgres
      MINIO_INTERNAL_URL: http://minio:9000
      MINIO_BUCKET: resumes
      OLLAMA_BASE_URL: http://ollama:11434
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
      redis:
        condition: service_healthy
```

---

### FIX-5 · `frontend/nginx.conf` — add missing API proxy routes

**File:** `frontend/nginx.conf`

**Why:** The nginx location regex only proxies 11 path prefixes. These are missing and currently return `index.html` (React app) instead of the API response:
- `/evaluations` — evaluation scoring (6-dimension ratings)
- `/notes` — recruiter notes + @mention notifications
- `/gdpr` — GDPR data export (admin-only)
- `/ai` — AI chat streaming (SSE)
- `/applications` — job application management
- `/resumes` — resume versioning

**Find:**
```nginx
    location ~ ^/(auth|files|jobs|candidates|comparisons|audit|users|notifications|analytics|parse|healthz)(/|$) {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
```

**Replace with:**
```nginx
    # Standard API routes
    location ~ ^/(auth|files|jobs|candidates|comparisons|audit|users|notifications|analytics|parse|healthz|evaluations|notes|gdpr|applications|resumes)(/|$) {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }

    # AI chat — SSE streaming needs buffering disabled
    location ~ ^/ai(/|$) {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
        proxy_buffering off;
        proxy_cache off;
        add_header X-Accel-Buffering no;
    }
```

Note: also bumped `proxy_read_timeout` from `120s` to `180s` to match `LLM_TIMEOUT_SECONDS=180` in config.

---

## HIGH FIXES — broken features

---

### FIX-6 · `.env.prod.example` — add LLM provider config

**File:** `.env.prod.example`

**Why:** App `config.py` defaults `llm_provider = "openai"`. If `OPENAI_API_KEY` is not set it raises `ValueError` at startup. If you want Ollama in prod (which is what `docker-compose.prod.yml` deploys) this must be explicit.

**Find:**
```
# ── Ollama (LLM) ──────────────────────────────────────────────────────────────
OLLAMA_MODEL=qwen2.5:7b
LLM_TIMEOUT_SECONDS=180
```

**Replace with:**
```
# ── LLM Provider ──────────────────────────────────────────────────────────────
# Use "ollama" for self-hosted (docker-compose.prod.yml ships with Ollama).
# Use "openai" if you have an OPENAI_API_KEY and want GPT-4o-mini.
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b
LLM_TIMEOUT_SECONDS=180

# Uncomment if switching to OpenAI:
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini
# OPENAI_EMBED_MODEL=text-embedding-3-small
```

---

### FIX-7 · Notifications — click to navigate + mark as read

**File:** `frontend/src/components/Layout/AppLayout.tsx`

**Why:** Clicking any notification does nothing. Users can't act on them. Also individual notifications are never marked read on click — only "Mark all read" works.

**Step 1 — add the `markRead` import** (it exists in the API but isn't imported here).

**Find:**
```typescript
import { getNotifications, markAllRead as markAllNotificationsRead } from '../../api/notifications';
```

**Replace with:**
```typescript
import { getNotifications, markRead as markNotificationRead, markAllRead as markAllNotificationsRead } from '../../api/notifications';
```

**Step 2 — add `getNotifLink` helper** after `formatRelativeTime`:

```typescript
function getNotifLink(n: Notification): string | null {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application' && p.job_id) return `/jobs/${p.job_id}`;
  if (n.type === 'stage_change' && p.candidate_id) return `/candidates/${p.candidate_id}`;
  if (n.type === 'rating_update' && p.candidate_id) return `/candidates/${p.candidate_id}`;
  if (n.type === 'mention' && p.candidate_id) return `/candidates/${p.candidate_id}`;
  return null;
}
```

**Step 3 — add `handleNotifClick` handler** inside the `AppLayout` component body, after `handleMarkAllRead`:

```typescript
  const handleNotifClick = async (item: Notification) => {
    setNotifOpen(false);
    if (!item.read_at) {
      try {
        await markNotificationRead(item.id);
        setNotifications((prev) =>
          prev.map((n) => (n.id === item.id ? { ...n, read_at: new Date().toISOString() } : n)),
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      } catch {
        // non-fatal — UI already closed
      }
    }
    const link = getNotifLink(item);
    if (link) navigate(link);
  };
```

**Step 4 — wire up click on each list item**.

**Find:**
```typescript
                      renderItem={(item) => (
                        <List.Item className={`notification-item${item.read_at ? '' : ' is-unread'}`}>
                          <List.Item.Meta
```

**Replace with:**
```typescript
                      renderItem={(item) => (
                        <List.Item
                          className={`notification-item${item.read_at ? '' : ' is-unread'}`}
                          onClick={() => handleNotifClick(item)}
                          style={{ cursor: getNotifLink(item) ? 'pointer' : 'default' }}
                        >
                          <List.Item.Meta
```

---

### FIX-8 · Notifications — `mention` type title + type icon

**File:** `frontend/src/components/Layout/AppLayout.tsx`

**Why:** `mention` notifications show raw `"mention"` string. Also all notifications look identical — no visual cue for type.

**Step 1 — fix `formatNotifTitle`**.

**Find:**
```typescript
function formatNotifTitle(n: Notification): string {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application') return `New application for "${p.job_title ?? 'a job'}"`;
  if (n.type === 'stage_change') {
    return `Stage → ${p.new_stage ?? '?'} for ${p.candidate_name ?? 'candidate'} (${p.job_title ?? ''})`;
  }
  if (n.type === 'rating_update') {
    return `Rating submitted for ${p.candidate_name ?? 'candidate'} — ${p.job_title ?? ''}`;
  }
  return n.type;
}
```

**Replace with:**
```typescript
const NOTIF_ICONS: Record<string, string> = {
  new_application: '📥',
  stage_change: '↕',
  rating_update: '⭐',
  mention: '@',
};

function getNotifIcon(type: string): string {
  return NOTIF_ICONS[type] ?? '🔔';
}

function formatNotifTitle(n: Notification): string {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application') return `New application for "${p.job_title ?? 'a job'}"`;
  if (n.type === 'stage_change') {
    return `Stage → ${p.new_stage ?? '?'} for ${p.candidate_name ?? 'candidate'} (${p.job_title ?? ''})`;
  }
  if (n.type === 'rating_update') {
    return `Rating submitted for ${p.candidate_name ?? 'candidate'} — ${p.job_title ?? ''}`;
  }
  if (n.type === 'mention') {
    return `${p.mentioned_by_name ?? 'Someone'} mentioned you on ${p.candidate_name ?? 'a candidate'}`;
  }
  return n.type;
}
```

**Step 2 — add icon + "See all" to notification panel**.

**Find:**
```typescript
                          <List.Item.Meta
                            title={
                              <span style={{ fontSize: 13, fontWeight: item.read_at ? 500 : 800 }}>
                                {formatNotifTitle(item)}
                              </span>
                            }
                            description={
                              <span style={{ fontSize: 12, color: '#64648a' }}>
                                {formatRelativeTime(item.created_at)}
                              </span>
                            }
                          />
```

**Replace with:**
```typescript
                          <List.Item.Meta
                            avatar={
                              <span style={{ fontSize: 14, opacity: item.read_at ? 0.5 : 1 }}>
                                {getNotifIcon(item.type)}
                              </span>
                            }
                            title={
                              <span style={{ fontSize: 13, fontWeight: item.read_at ? 500 : 700 }}>
                                {formatNotifTitle(item)}
                              </span>
                            }
                            description={
                              <span style={{ fontSize: 12, color: '#64648a' }}>
                                {formatRelativeTime(item.created_at)}
                              </span>
                            }
                          />
```

**Step 3 — constrain panel width + add "See all" footer**.

**Find:**
```typescript
                  <div className="notification-panel">
                    <List
                      size="small"
                      dataSource={notifications}
                      locale={{ emptyText: 'No notifications' }}
                      renderItem={(item) => (
```

**Replace with:**
```typescript
                  <div className="notification-panel" style={{ width: 340, maxHeight: 420, overflowY: 'auto' }}>
                    <List
                      size="small"
                      dataSource={notifications}
                      locale={{ emptyText: 'No notifications' }}
                      renderItem={(item) => (
```

Add a footer **after** the closing `</List>` tag and before `</div>`:

```typescript
                    {notifications.length > 0 && (
                      <div
                        style={{
                          padding: '8px 12px',
                          borderTop: '1px solid rgba(255,255,255,0.07)',
                          textAlign: 'center',
                        }}
                      >
                        <Button
                          type="link"
                          size="small"
                          style={{ fontSize: 12, color: '#5b6af5' }}
                          onClick={() => { setNotifOpen(false); navigate('/notifications'); }}
                        >
                          See all notifications
                        </Button>
                      </div>
                    )}
```

> Note: `/notifications` page doesn't exist yet — see FIX-9 below. The button won't crash; it just navigates to root (PrivateRoute redirects).

---

### FIX-9 · Add `/notifications` page and route

**Why:** "See all" from the panel needs a destination. The popover only shows 10 items; recruiters with heavy activity need to scroll history.

**Step 1 — Create `frontend/src/pages/Notifications.tsx`:**

```typescript
import { useState } from 'react';
import { List, Button, Badge, Empty } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getNotifications, markRead, markAllRead } from '../api/notifications';
import type { Notification } from '../types';

const NOTIF_ICONS: Record<string, string> = {
  new_application: '📥',
  stage_change: '↕',
  rating_update: '⭐',
  mention: '@',
};

function notifLink(n: Notification): string | null {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application' && p.job_id) return `/jobs/${p.job_id}`;
  if ((n.type === 'stage_change' || n.type === 'rating_update' || n.type === 'mention') && p.candidate_id)
    return `/candidates/${p.candidate_id}`;
  return null;
}

function formatTitle(n: Notification): string {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application') return `New application for "${p.job_title ?? 'a job'}"`;
  if (n.type === 'stage_change')
    return `Stage → ${p.new_stage ?? '?'} for ${p.candidate_name ?? 'candidate'} (${p.job_title ?? ''})`;
  if (n.type === 'rating_update')
    return `Rating submitted for ${p.candidate_name ?? 'candidate'} — ${p.job_title ?? ''}`;
  if (n.type === 'mention')
    return `${p.mentioned_by_name ?? 'Someone'} mentioned you on ${p.candidate_name ?? 'a candidate'}`;
  return n.type;
}

function timeAgo(iso: string): string {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function Notifications() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', 'all'],
    queryFn: () => getNotifications({ limit: 50 }),
  });

  const markReadMutation = useMutation({
    mutationFn: markRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });

  const markAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });

  const items = data?.items ?? [];
  const unread = data?.unread_count ?? 0;

  const handleClick = (item: Notification) => {
    if (!item.read_at) markReadMutation.mutate(item.id);
    const link = notifLink(item);
    if (link) navigate(link);
  };

  return (
    <div className="page-shell">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <BellOutlined style={{ fontSize: 18, color: '#5b6af5' }} />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Notifications</h2>
          {unread > 0 && <Badge count={unread} />}
        </div>
        {unread > 0 && (
          <Button
            size="small"
            onClick={() => markAllMutation.mutate()}
            loading={markAllMutation.isPending}
          >
            Mark all read
          </Button>
        )}
      </div>

      <div className="data-panel">
        {items.length === 0 && !isLoading ? (
          <Empty description="No notifications" style={{ padding: '48px 0' }} />
        ) : (
          <List
            loading={isLoading}
            dataSource={items}
            renderItem={(item) => (
              <List.Item
                onClick={() => handleClick(item)}
                style={{
                  cursor: notifLink(item) ? 'pointer' : 'default',
                  padding: '12px 16px',
                  background: item.read_at ? 'transparent' : 'rgba(91,106,245,0.06)',
                  borderLeft: item.read_at ? '3px solid transparent' : '3px solid #5b6af5',
                  transition: 'background 0.15s',
                }}
              >
                <List.Item.Meta
                  avatar={
                    <span style={{ fontSize: 16, opacity: item.read_at ? 0.45 : 1 }}>
                      {NOTIF_ICONS[item.type] ?? '🔔'}
                    </span>
                  }
                  title={
                    <span style={{ fontWeight: item.read_at ? 500 : 700, fontSize: 14 }}>
                      {formatTitle(item)}
                    </span>
                  }
                  description={
                    <span style={{ fontSize: 12, color: '#64648a' }}>{timeAgo(item.created_at)}</span>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );
}
```

**Step 2 — register the route in `frontend/src/App.tsx`:**

Add the import at the top:
```typescript
import Notifications from './pages/Notifications';
```

**Find:**
```typescript
                <Route path="admin/audit" element={<AuditLog />} />
```

**Add after it:**
```typescript
                <Route path="notifications" element={<Notifications />} />
```

---

### FIX-10 · CandidateList — wire stage filter to API

**File:** `frontend/src/pages/CandidateList.tsx`

**Why:** `stageFilter` state is set by pill buttons but never included in `structuredFilters`. Clicking "Hired" shows all candidates, not hired ones.

**Step 1 — fix `STAGE_FILTERS` to use real API status values.**

**Find:**
```typescript
const STAGE_FILTERS = [
  { label: 'All stages', value: undefined as string | undefined },
  { label: 'Reviewing', value: 'active' },
  { label: 'Shortlisted', value: 'active' },
  { label: 'Interview', value: 'active' },
  { label: 'Offer', value: 'active' },
  { label: 'Hired', value: 'hired' },
] as const;
```

**Replace with:**
```typescript
const STAGE_FILTERS: { label: string; value: string | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Active', value: 'active' },
  { label: 'Hired', value: 'hired' },
  { label: 'Archived', value: 'archived' },
];
```

> Why: the backend `GET /candidates/search` accepts a `status` param matching candidate `status` column values: `active | hired | archived`. Application-level stages (reviewing/interview/offer) live on `job_applications`, not on candidates directly — you can't filter candidates by those in one query without a join. Keep it simple: Active / Hired / Archived map cleanly to the API.

**Step 2 — change `stageFilter` type and default.**

**Find:**
```typescript
  const [stageFilter, setStageFilter] = useState<string>('All stages');
```

**Replace with:**
```typescript
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
```

**Step 3 — include `statusFilter` in `structuredFilters`.**

**Find:**
```typescript
  const structuredFilters: CandidateSearchFilters = useMemo(
    () => ({
      q: debouncedQ || undefined,
      skills: skills.length > 0 ? skills : undefined,
      seniority: seniority || undefined,
      page,
      size: PAGE_SIZE,
    }),
    [debouncedQ, skills, seniority, page],
  );
```

**Replace with:**
```typescript
  const structuredFilters: CandidateSearchFilters = useMemo(
    () => ({
      q: debouncedQ || undefined,
      skills: skills.length > 0 ? skills : undefined,
      seniority: seniority || undefined,
      status: statusFilter,
      page,
      size: PAGE_SIZE,
    }),
    [debouncedQ, skills, seniority, statusFilter, page],
  );
```

**Step 4 — reset page on filter change.**

**Find:**
```typescript
  useEffect(() => {
    setPage(1);
  }, [debouncedQ, skills, seniority]);
```

**Replace with:**
```typescript
  useEffect(() => {
    setPage(1);
  }, [debouncedQ, skills, seniority, statusFilter]);
```

**Step 5 — update the pill button render.**

**Find:**
```typescript
        <div className="clist-pill-group">
          {STAGE_FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={`clist-pill${stageFilter === f.label ? ' is-active' : ''}`}
              onClick={() => setStageFilter(f.label)}
            >
              {f.label}
            </button>
          ))}
        </div>
```

**Replace with:**
```typescript
        <div className="clist-pill-group">
          {STAGE_FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={`clist-pill${statusFilter === f.value ? ' is-active' : ''}`}
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
```

**Step 6 — add `status` to `CandidateSearchFilters` type (if not already there).**

**File:** `frontend/src/types/index.ts`

**Find:**
```typescript
export interface CandidateSearchFilters {
  q?: string;
  skills?: string[];
  seniority?: string;
  location?: string;
  years_min?: number;
  years_max?: number;
  page?: number;
  size?: number;
}
```

**Replace with:**
```typescript
export interface CandidateSearchFilters {
  q?: string;
  skills?: string[];
  seniority?: string;
  status?: string;
  location?: string;
  years_min?: number;
  years_max?: number;
  page?: number;
  size?: number;
}
```

---

## MEDIUM FIXES — UX + ops polish

---

### FIX-11 · Sidebar — "AI Screening" dead item

**File:** `frontend/src/components/Layout/AppLayout.tsx`

**Why:** The button renders, users click it, nothing happens. Looks broken.

**Option A (remove it):**

**Find:**
```typescript
const BASE_NAV: NavItem[] = [
  { key: '/analytics', icon: <AppstoreOutlined />, label: 'Overview' },
  { key: '/', icon: <UserOutlined />, label: 'Candidates' },
  { key: '/jobs', icon: <SolutionOutlined />, label: 'Jobs' },
  { key: '/pipeline-nav', icon: <ProjectOutlined />, label: 'Pipeline' },
  { key: '/ai-screening', icon: <ThunderboltOutlined />, label: 'AI Screening' },
];
```

**Replace with:**
```typescript
const BASE_NAV: NavItem[] = [
  { key: '/analytics', icon: <AppstoreOutlined />, label: 'Overview' },
  { key: '/', icon: <UserOutlined />, label: 'Candidates' },
  { key: '/jobs', icon: <SolutionOutlined />, label: 'Jobs' },
  { key: '/pipeline-nav', icon: <ProjectOutlined />, label: 'Pipeline' },
];
```

And remove the `ThunderboltOutlined` import if no longer used.

**Option B (keep with tooltip):** Update `Tooltip` to say `"AI Screening (coming soon)"` and keep the disabled state. Either is fine — removing is cleaner.

---

### FIX-12 · Sidebar — Pipeline nav goes to /jobs

**File:** `frontend/src/components/Layout/AppLayout.tsx`

**Why:** Clicking "Pipeline" navigates to the jobs list. Makes sense since pipeline is per-job, but the nav item is confusing. Two options:

**Option A — remove Pipeline from sidebar** (cleanest):
Remove `{ key: '/pipeline-nav', icon: <ProjectOutlined />, label: 'Pipeline' }` from `BASE_NAV`. Pipeline is accessible from every Job card via the "Pipeline" button. Nav item is redundant.

**Option B — keep, update tooltip:**
Change label from `'Pipeline'` to `'Pipeline (select a job)'` and add tooltip text `"Open a job to view its pipeline"`.

---

### FIX-13 · Header "New role" button

**File:** `frontend/src/components/Layout/AppLayout.tsx`

**Why:** Button says "New role" but navigates to the jobs list — user has to then find a "Create" button. Should open the create-job modal directly.

Check how `JobList.tsx` manages the create modal. If it uses a URL param:

**Find in `AppLayout.tsx`:**
```typescript
              <Button
                type="primary"
                icon={<PlusOutlined />}
                className="header-cta-btn"
                onClick={() => navigate('/jobs')}
                aria-label="New role"
              >
                New role
              </Button>
```

**Replace with:**
```typescript
              <Button
                type="primary"
                icon={<PlusOutlined />}
                className="header-cta-btn"
                onClick={() => navigate('/jobs?create=true')}
                aria-label="New role"
              >
                New role
              </Button>
```

Then in **`frontend/src/pages/JobList.tsx`**, read the `?create=true` param on mount and auto-open the create modal:

```typescript
import { useSearchParams } from 'react-router-dom';

// Inside JobList component:
const [searchParams, setSearchParams] = useSearchParams();

useEffect(() => {
  if (searchParams.get('create') === 'true') {
    setCreateModalOpen(true);
    setSearchParams({}, { replace: true });
  }
}, []);
```

> If `JobList` doesn't already have a create modal — check current code before applying. If the create form is inline, just navigate to `/jobs` and it's acceptable for now.

---

### FIX-14 · Dockerfile — non-root user

**File:** `Dockerfile`

**Why:** Running as root in a container means a container escape gives root on the host.

**Find:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

**Replace with:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

---

### FIX-15 · LLM client singleton

**File:** `app/llm/factory.py`

**Why:** Every call to `get_llm_client()` creates a new `AsyncOpenAI` client (or new `OllamaClient` with new `httpx.AsyncClient`). Under load, this means hundreds of unclosed HTTP clients. Should be created once.

**Find:**
```python
from typing import Literal

from app.config import settings
from app.llm.ollama import OllamaClient
from app.llm.openai_client import OpenAIClient

LLMClient = OllamaClient | OpenAIClient


def get_llm_client() -> LLMClient:
    provider: Literal["ollama", "openai"] = settings.llm_provider  # type: ignore[assignment]
    if provider == "openai":
        return OpenAIClient()
    return OllamaClient()
```

**Replace with:**
```python
from typing import Literal

from app.config import settings
from app.llm.ollama import OllamaClient
from app.llm.openai_client import OpenAIClient

LLMClient = OllamaClient | OpenAIClient

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        provider: Literal["ollama", "openai"] = settings.llm_provider  # type: ignore[assignment]
        _client = OpenAIClient() if provider == "openai" else OllamaClient()
    return _client
```

---

### FIX-16 · `cookie_secure` in prod compose

**File:** `docker-compose.prod.yml`

**Why:** `app/config.py` has `cookie_secure: bool = False`. Prod serves HTTPS via Traefik, but the backend container env doesn't set `COOKIE_SECURE=true`. Refresh token cookies will be sent as non-secure, making them vulnerable to MITM on any HTTP interception point.

Add to the `backend` service `environment` block:
```yaml
      COOKIE_SECURE: "true"
```

And add the same to the `worker` service if it ever issues cookies (it doesn't, but consistent env is good practice).

---

### FIX-17 · README rewrite (high-level outline)

**File:** `README.md`

The current README describes Sprint 1 state. Replace the body with:

```markdown
# AI-Based Recruitment Platform

AI-powered candidate management for AI_Based_recruitment. Upload resumes → LLM parses → rank candidates per job → track through hiring pipeline.

**Stack:** Python 3.12 · FastAPI · PostgreSQL 16 + pgvector · MinIO · Celery + Redis · React 18 · Ant Design · Vite · Docker

## Local Dev (5 commands)

\`\`\`powershell
cp .env.example .env          # fill in values
docker compose up -d          # postgres + minio + redis + mailpit
uv run alembic upgrade head   # run all 30 migrations
uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev    # :3000
# Celery worker (separate terminal):
uv run celery -A app.worker.celery_app worker -l info
\`\`\`

Create first admin: `uv run python scripts/create_admin.py`

## Production Deploy

\`\`\`bash
cp .env.prod.example .env.prod   # fill APP_DOMAIN, secrets, LLM vars
docker compose -f docker-compose.prod.yml up -d --build
\`\`\`

Traefik auto-provisions TLS via Let's Encrypt. App at `https://$APP_DOMAIN`.

## Key Features

| Feature | Where |
|---------|-------|
| Resume upload + LLM parse | `POST /files/upload` → `POST /parse` |
| AI scoring per job | Celery `score_candidates_for_job_task` |
| Candidate comparison + verdict | `POST /jobs/{id}/comparisons` |
| Kanban pipeline | `frontend/src/pages/Pipeline.tsx` |
| Notifications + @mentions | `app/notifications/` |
| RBAC (admin/recruiter/hr_manager/viewer) | `app/users/models.py` → `UserRole` |
| GDPR data export | `GET /gdpr/candidates/{id}/export` |
| Audit log | `GET /audit/logs` + `GET /audit/business-events` |

## Architecture

Modular monolith. One FastAPI process, one Celery worker, PostgreSQL + MinIO + Redis.
See Obsidian `02 - Architecture.md` for full system diagram.

## Migrations

Chain: `0001 → … → 0030` (30 migrations). Current head: `0030_candidate_photo_url`.
Run: `uv run alembic upgrade head`

## Tests

\`\`\`
uv run pytest                   # all 212 tests
uv run pytest tests/test_auth.py -v
\`\`\`
```

---

## VERIFICATION CHECKLIST

After all fixes, run through this manually:

```
[ ] docker compose -f docker-compose.prod.yml config   # no YAML errors
[ ] docker compose -f docker-compose.prod.yml up -d --build
[ ] curl https://$APP_DOMAIN/healthz                   # {"status":"ok"}
[ ] curl https://$APP_DOMAIN/auth/login -d '{...}'    # JWT returned (not index.html)
[ ] curl https://$APP_DOMAIN/evaluations               # 401 not index.html
[ ] curl https://$APP_DOMAIN/notes                     # 401 not index.html
[ ] curl https://$APP_DOMAIN/ai/chat                   # 401 not index.html
[ ] Upload resume to a job → status goes parsing → applied (Celery working)
[ ] Click a notification → navigates to correct page + notification goes dim
[ ] "All / Active / Hired / Archived" pills filter the candidate list
[ ] AI chat streams (text appears word-by-word, not in one dump)
```

---

## ISSUE → FIX QUICK REFERENCE

| Issue ID | File | Fix # |
|----------|------|-------|
| pgvector image | `docker-compose.prod.yml` | FIX-1 |
| redis missing | `docker-compose.prod.yml` | FIX-2 |
| celery worker missing | `docker-compose.prod.yml` | FIX-3 |
| missing env vars | `docker-compose.prod.yml` | FIX-4 |
| nginx missing routes | `frontend/nginx.conf` | FIX-5 |
| LLM vars in prod env | `.env.prod.example` | FIX-6 |
| notification click | `AppLayout.tsx` | FIX-7 |
| mention title + icons | `AppLayout.tsx` | FIX-8 |
| notifications page | new `Notifications.tsx` + `App.tsx` | FIX-9 |
| stage filter disconnected | `CandidateList.tsx` + `types/index.ts` | FIX-10 |
| AI Screening dead item | `AppLayout.tsx` | FIX-11 |
| Pipeline nav | `AppLayout.tsx` | FIX-12 |
| New role button | `AppLayout.tsx` + `JobList.tsx` | FIX-13 |
| root user in Docker | `Dockerfile` | FIX-14 |
| LLM client singleton | `app/llm/factory.py` | FIX-15 |
| cookie_secure | `docker-compose.prod.yml` | FIX-16 |
| README | `README.md` | FIX-17 |
