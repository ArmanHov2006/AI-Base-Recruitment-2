import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Skeleton, Tooltip, InputNumber, Drawer, Table, Tag, message } from 'antd';
import type { TableColumnsType } from 'antd';
import {
  ArrowLeftOutlined,
  CodeOutlined,
  BarChartOutlined,
  TeamOutlined,
  InfoCircleOutlined,
  EditOutlined,
  SaveOutlined,
  CloseOutlined,
  FilePdfOutlined,
  ExperimentOutlined,
  InboxOutlined,
} from '@ant-design/icons';
import { getJob, getJobLeaderboard, getJobAnalyticsSummary, patchJob } from '../api/jobs';
import { downloadQualifiedCandidatesPdf } from '../api/pdf';
import type { LeaderboardEntry, UpdateJobRequest } from '../types';

// ─── helpers ──────────────────────────────────────────────────────────────────

// overall_score in DB is 0–100; toDisplay converts to the 0–10 display scale
function toDisplay(raw: number | null): number | null {
  return raw != null ? Math.round(raw) / 10 : null;
}

interface Bucket {
  score: number;
  label: string;
  count: number;
}

function buildBuckets(entries: { display: number | null }[]): Bucket[] {
  const map: Record<number, number> = {};
  for (let s = 0; s <= 10; s += 0.5) {
    map[s] = 0;
  }
  for (const e of entries) {
    if (e.display != null) {
      const key = Math.round(e.display * 2) / 2;
      const clamped = Math.max(0, Math.min(10, key));
      map[clamped] = (map[clamped] ?? 0) + 1;
    }
  }
  return Object.entries(map)
    .map(([k, v]) => ({ score: parseFloat(k), label: parseFloat(k).toFixed(1), count: v }))
    .sort((a, b) => a.score - b.score);
}

// ─── SVG chart ────────────────────────────────────────────────────────────────

interface ChartProps {
  buckets: Bucket[];
  threshold: number;
}

function ScoreChart({ buckets, threshold }: ChartProps) {
  const L = 42, R = 16, T = 16, B = 44;
  const SVG_W = 580;
  const SVG_H = 280;
  const W = SVG_W - L - R;
  const H = SVG_H - T - B;

  const maxCount = Math.max(...buckets.map(b => b.count), 1);
  const barW = W / buckets.length;
  const gap = Math.max(1, barW * 0.12);

  const xForScore = (s: number) => L + (s / 10) * W;
  const yForCount = (c: number) => T + H - (c / maxCount) * H;

  const yTicks = maxCount <= 4
    ? Array.from({ length: maxCount + 1 }, (_, i) => i)
    : [0, Math.round(maxCount / 4), Math.round(maxCount / 2), Math.round((maxCount * 3) / 4), maxCount];

  const xLabels = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  const thresholdX = xForScore(threshold);

  return (
    <svg
      viewBox={`0 0 ${SVG_W} ${SVG_H}`}
      style={{ width: '100%', height: 'auto', overflow: 'visible' }}
      aria-label="Score distribution chart"
    >
      <rect x={L} y={T} width={W} height={H} fill="rgba(255,255,255,0.02)" rx={4} />

      {yTicks.map(t => (
        <line
          key={t}
          x1={L} y1={yForCount(t)}
          x2={L + W} y2={yForCount(t)}
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={1}
        />
      ))}

      <rect
        x={thresholdX}
        y={T}
        width={L + W - thresholdX}
        height={H}
        fill="rgba(91,106,245,0.04)"
      />

      {buckets.map((b, i) => {
        const x = L + i * barW + gap;
        const w = barW - gap * 2;
        const barH = b.count > 0 ? (b.count / maxCount) * H : 0;
        const y = T + H - barH;
        const qualified = b.score >= threshold;
        return (
          <g key={b.score}>
            <rect
              x={x} y={y}
              width={Math.max(w, 0)} height={barH}
              fill={qualified ? '#5b6af5' : 'rgba(91,106,245,0.28)'}
              rx={2}
            />
            {b.count > 0 && (
              <text
                x={x + w / 2} y={y - 4}
                fill={qualified ? '#a0aaff' : '#64648a'}
                fontSize={9}
                textAnchor="middle"
              >
                {b.count}
              </text>
            )}
          </g>
        );
      })}

      <line
        x1={thresholdX} y1={T}
        x2={thresholdX} y2={T + H}
        stroke="#5b6af5"
        strokeWidth={1.5}
        strokeDasharray="5 3"
      />
      <text
        x={thresholdX + 5} y={T + 14}
        fill="#5b6af5"
        fontSize={11}
        fontWeight={700}
      >
        Threshold {threshold.toFixed(1)}
      </text>

      {yTicks.map(t => (
        <text
          key={t}
          x={L - 6} y={yForCount(t) + 4}
          fill="#64648a"
          fontSize={10}
          textAnchor="end"
        >
          {t}
        </text>
      ))}

      <text
        x={11}
        y={T + H / 2}
        fill="#64648a"
        fontSize={10}
        textAnchor="middle"
        transform={`rotate(-90, 11, ${T + H / 2})`}
      >
        Candidates
      </text>

      {xLabels.map(v => (
        <text
          key={v}
          x={xForScore(v)}
          y={T + H + 18}
          fill="#64648a"
          fontSize={10}
          textAnchor="middle"
        >
          {v.toFixed(1)}
        </text>
      ))}

      <text
        x={L + W / 2}
        y={SVG_H - 4}
        fill="#64648a"
        fontSize={10}
        textAnchor="middle"
      >
        Score (out of 10)
      </text>

      <line x1={L} y1={T} x2={L} y2={T + H} stroke="rgba(255,255,255,0.12)" strokeWidth={1} />
      <line x1={L} y1={T + H} x2={L + W} y2={T + H} stroke="rgba(255,255,255,0.12)" strokeWidth={1} />
    </svg>
  );
}

// ─── stat card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  loading: boolean;
}

function StatCard({ label, value, loading }: StatCardProps) {
  return (
    <div className="ra-stat-card">
      <span className="ra-stat-label">{label}</span>
      {loading ? (
        <div style={{ marginTop: 8 }}>
          <Skeleton.Input active size="small" style={{ width: 80 }} />
        </div>
      ) : (
        <div className="ra-stat-value">{value}</div>
      )}
    </div>
  );
}

// ─── empty state ──────────────────────────────────────────────────────────────

interface EmptyStateProps {
  icon: React.ComponentType<{ style?: React.CSSProperties }>;
  title: string;
  sub: string;
}

function EmptyState({ icon: Icon, title, sub }: EmptyStateProps) {
  return (
    <div className="ra-empty-state">
      <Icon style={{ fontSize: 32, color: '#3c3c5a', marginBottom: 12 }} />
      <div className="ra-empty-title">{title}</div>
      <div className="ra-empty-sub">{sub}</div>
    </div>
  );
}

// ─── pipeline status helpers ───────────────────────────────────────────────────

function getPipelineStatus(qualified: number, target: number): {
  label: 'Underfilled' | 'On Track' | 'Overfilled';
  color: string;
  description: string;
} {
  const pct = target > 0 ? qualified / target : 1;
  if (pct >= 1) return { label: 'Overfilled', color: '#34d399', description: 'You have met or exceeded your interview target.' };
  if (pct >= 0.8) return { label: 'On Track', color: '#fbbf24', description: 'You are close to reaching your target.' };
  return { label: 'Underfilled', color: '#5b6af5', description: 'You need more qualified candidates to reach your target.' };
}

// ─── types ────────────────────────────────────────────────────────────────────

type QualEntry = LeaderboardEntry & { display: number | null };

// ─── main page ────────────────────────────────────────────────────────────────

export default function RoleAnalytics() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [editMode, setEditMode] = useState<'threshold' | 'target' | null>(null);
  const [draftValue, setDraftValue] = useState<number | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<QualEntry | null>(null);
  const [exportingPdf, setExportingPdf] = useState(false);

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    retry: false,
  });

  const { data: rawEntries = [], isLoading: entriesLoading } = useQuery({
    queryKey: ['leaderboard', jobId],
    queryFn: () => getJobLeaderboard(jobId!),
    enabled: !!jobId,
    staleTime: 30_000,
  });

  const { data: summary } = useQuery({
    queryKey: ['job-analytics-summary', jobId],
    queryFn: () => getJobAnalyticsSummary(jobId!),
    enabled: !!jobId,
    staleTime: 30_000,
  });

  const patchMutation = useMutation({
    mutationFn: (data: UpdateJobRequest) => patchJob(jobId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', jobId] });
      setEditMode(null);
      setDraftValue(null);
    },
    onError: () => {
      message.error('Failed to save changes. Please try again.');
    },
  });

  const isLoading = jobLoading || entriesLoading;

  const hasThreshold = job?.threshold_score != null;
  const threshold = job?.threshold_score ?? 7.5;
  const hasTarget = job?.candidates_for_next_stage != null;
  const target = job?.candidates_for_next_stage ?? 30;
  const totalApplications = summary?.total_applications ?? 0;
  const scoredCount = summary?.scored_count ?? 0;
  const unscoredCount = Math.max(0, totalApplications - scoredCount);

  const entries: QualEntry[] = rawEntries.map(e => ({
    ...e,
    display: toDisplay(e.overall_score),
  }));

  const qualified = entries
    .filter(e => e.display != null && e.display >= threshold)
    .sort((a, b) => (b.display ?? 0) - (a.display ?? 0));

  const fillPct = target > 0 ? Math.min((qualified.length / target) * 100, 100) : 0;
  const missing = Math.max(0, target - qualified.length);
  const status = getPipelineStatus(qualified.length, target);
  const buckets = buildBuckets(entries);

  const handleSave = () => {
    if (draftValue === null) return;
    if (editMode === 'threshold') {
      patchMutation.mutate({ threshold_score: draftValue });
    } else if (editMode === 'target') {
      patchMutation.mutate({ candidates_for_next_stage: Math.round(draftValue) });
    }
  };

  const handleCancelEdit = () => {
    setEditMode(null);
    setDraftValue(null);
  };

  const handleExportPdf = async () => {
    setExportingPdf(true);
    try {
      await downloadQualifiedCandidatesPdf(jobId!, threshold);
    } catch {
      message.error('PDF export failed. Please try again.');
    } finally {
      setExportingPdf(false);
    }
  };

  // ── inline edit value builders ─────────────────────────────────────────────

  const thresholdValue =
    editMode === 'threshold' ? (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <InputNumber
          min={0} max={10} step={0.5} precision={1}
          value={draftValue as number}
          onChange={val => setDraftValue(val)}
          style={{ width: 82 }}
          autoFocus
          onPressEnter={handleSave}
        />
        <Button size="small" type="primary" icon={<SaveOutlined />}
          loading={patchMutation.isPending} onClick={handleSave} />
        <Button size="small" icon={<CloseOutlined />} onClick={handleCancelEdit} />
      </div>
    ) : (
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        {!hasThreshold ? (
          <span style={{ fontSize: 13, color: '#64648a', fontStyle: 'italic' }}>Not set</span>
        ) : (
          <>
            <span style={{ fontSize: 28, fontWeight: 800, fontFamily: 'Fira Code, monospace', color: '#ededf5' }}>
              {threshold.toFixed(1)}
            </span>
            <span style={{ fontSize: 14, color: '#64648a' }}>/ 10</span>
          </>
        )}
        <Button
          type="text" size="small" icon={<EditOutlined />}
          style={{ color: '#64648a', padding: '0 4px', height: 'auto', lineHeight: 1 }}
          onClick={() => { setEditMode('threshold'); setDraftValue(hasThreshold ? threshold : 7.5); }}
        />
      </div>
    );

  const targetValue =
    editMode === 'target' ? (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <InputNumber
          min={1} max={1000} precision={0}
          value={draftValue as number}
          onChange={val => setDraftValue(val)}
          style={{ width: 82 }}
          autoFocus
          onPressEnter={handleSave}
        />
        <Button size="small" type="primary" icon={<SaveOutlined />}
          loading={patchMutation.isPending} onClick={handleSave} />
        <Button size="small" icon={<CloseOutlined />} onClick={handleCancelEdit} />
      </div>
    ) : (
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        {!hasTarget ? (
          <span style={{ fontSize: 13, color: '#64648a', fontStyle: 'italic' }}>Not set</span>
        ) : (
          <span style={{ fontSize: 28, fontWeight: 800, fontFamily: 'Fira Code, monospace', color: '#ededf5' }}>
            {target}
          </span>
        )}
        <Button
          type="text" size="small" icon={<EditOutlined />}
          style={{ color: '#64648a', padding: '0 4px', height: 'auto', lineHeight: 1 }}
          onClick={() => { setEditMode('target'); setDraftValue(hasTarget ? target : 30); }}
        />
      </div>
    );

  // ── qualified table columns ────────────────────────────────────────────────

  const qualColumns: TableColumnsType<QualEntry> = [
    {
      title: '#',
      key: 'rank',
      width: 44,
      render: (_val, _rec, idx) => (
        <span style={{ color: '#64648a', fontSize: 12, fontFamily: 'Fira Code, monospace' }}>
          {idx + 1}
        </span>
      ),
    },
    {
      title: 'Candidate',
      dataIndex: 'candidate_name',
      key: 'name',
      render: (name: string | null) => name || 'Unnamed',
    },
    {
      title: 'Seniority',
      dataIndex: 'candidate_seniority',
      key: 'seniority',
      width: 110,
      render: (val: string | null) =>
        val ? (
          <Tag style={{ fontSize: 11, lineHeight: '18px' }}>{val}</Tag>
        ) : null,
    },
    {
      title: 'Score',
      key: 'score',
      width: 76,
      defaultSortOrder: 'descend',
      sorter: (a: QualEntry, b: QualEntry) => (a.display ?? 0) - (b.display ?? 0),
      render: (_val: unknown, record: QualEntry) => (
        <span style={{ fontFamily: 'Fira Code, monospace', fontWeight: 700, color: '#34d399' }}>
          {record.display?.toFixed(1)}
        </span>
      ),
    },
  ];

  if (!jobLoading && !job) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <p style={{ color: '#64648a' }}>Job not found.</p>
        <Button onClick={() => navigate('/jobs')}>Back to Jobs</Button>
      </div>
    );
  }

  // ── empty state for score distribution ────────────────────────────────────

  const chartEmptyState =
    totalApplications === 0 ? (
      <EmptyState
        icon={InboxOutlined}
        title="No applicants yet"
        sub="Candidates will appear here once they apply to this role."
      />
    ) : (
      <EmptyState
        icon={ExperimentOutlined}
        title="Scoring in progress"
        sub="Candidates have applied but scoring hasn't run yet. Start a comparison to generate scores."
      />
    );

  return (
    <div className="page-shell">

      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#64648a' }}>
        <span
          role="link" tabIndex={0}
          style={{ cursor: 'pointer', color: '#5b6af5', fontWeight: 500 }}
          onClick={() => navigate('/jobs')}
          onKeyDown={e => { if (e.key === 'Enter') navigate('/jobs'); }}
        >
          Jobs
        </span>
        <span>/</span>
        <span
          role="link" tabIndex={0}
          style={{ cursor: 'pointer', color: '#5b6af5', fontWeight: 500 }}
          onClick={() => navigate(`/jobs/${jobId}`)}
          onKeyDown={e => { if (e.key === 'Enter') navigate(`/jobs/${jobId}`); }}
        >
          {job?.title ?? '…'}
        </span>
        <span>/</span>
        <span style={{ color: '#ededf5', fontWeight: 600 }} aria-current="page">Role Analytics</span>
      </div>

      {/* ── Header card ─────────────────────────────────────────────────────── */}
      <div className="data-panel ra-header-card">
        <div className="ra-job-identity">
          <div className="ra-job-icon">
            <CodeOutlined style={{ fontSize: 22, color: '#5b6af5' }} />
          </div>
          <div>
            {jobLoading ? (
              <Skeleton.Input active size="default" style={{ width: 200 }} />
            ) : (
              <h1 className="ra-job-title">{job?.title}</h1>
            )}
            <p className="ra-job-subtitle">Role Overview</p>
          </div>
        </div>

        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(`/jobs/${jobId}`)}
          style={{ marginLeft: 'auto', marginRight: 16, flexShrink: 0 }}
          aria-label="Back to job"
        />

        <StatCard label="Threshold Score" loading={jobLoading} value={thresholdValue} />
        <StatCard label="Target Interviews" loading={jobLoading} value={targetValue} />
        <StatCard
          label="Qualified"
          loading={isLoading}
          value={
            <span style={{ fontSize: 28, fontWeight: 800, fontFamily: 'Fira Code, monospace', color: '#34d399' }}>
              {qualified.length}
            </span>
          }
        />
        <StatCard
          label="Awaiting Scoring"
          loading={isLoading || !summary}
          value={
            <span style={{ fontSize: 28, fontWeight: 800, fontFamily: 'Fira Code, monospace', color: unscoredCount > 0 ? '#fbbf24' : '#64648a' }}>
              {unscoredCount}
            </span>
          }
        />
      </div>

      {/* ── Pipeline Fill ────────────────────────────────────────────────────── */}
      <div className="data-panel ra-pipeline-card">
        <div className="ra-pipeline-meta">
          <div>
            <div className="ra-section-title">Pipeline Fill</div>
            <div className="ra-section-sub">
              Progress toward interview target
              {!hasTarget && <span style={{ color: '#64648a', fontSize: 11, marginLeft: 6 }}>(using default target of 30)</span>}
            </div>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'Fira Code, monospace', color: '#ededf5' }}>
              {isLoading ? '—' : `${qualified.length} / ${target}`}
            </div>
            <div style={{ fontSize: 12, color: '#64648a', marginTop: 2 }}>
              {isLoading ? '' : `${Math.round(fillPct)}% of target`}
            </div>
          </div>
        </div>

        <div className="ra-progress-track">
          <div
            className="ra-progress-fill"
            style={{ width: isLoading ? '0%' : `${fillPct}%` }}
          />
        </div>

        <div className="ra-progress-labels">
          <span>0</span>
          {!isLoading && qualified.length > 0 && qualified.length < target && (
            <span style={{ marginLeft: `${fillPct}%`, transform: 'translateX(-50%)', position: 'absolute' }}>
              {qualified.length}
            </span>
          )}
          <span style={{ marginLeft: 'auto' }}>
            {target}{hasTarget ? ' (Target)' : ' (Default)'}
          </span>
        </div>
      </div>

      {/* ── Chart + Insight row ───────────────────────────────────────────────── */}
      <div className="ra-bottom-row">

        <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Score Distribution */}
          <div className="data-panel" style={{ padding: '20px 20px 12px' }}>
            <div style={{ marginBottom: 12 }}>
              <div className="ra-section-title">Score Distribution</div>
              <div className="ra-section-sub">All scored candidates by score bucket</div>
            </div>
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 6 }} />
            ) : entries.length === 0 ? (
              chartEmptyState
            ) : (
              <ScoreChart buckets={buckets} threshold={threshold} />
            )}
          </div>

          {/* Qualified Candidates Table */}
          <div className="data-panel" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
              <div className="ra-section-title">
                Qualified Candidates
                <span style={{ fontSize: 13, fontWeight: 400, color: '#64648a', marginLeft: 8 }}>
                  Score &ge; {threshold.toFixed(1)}
                  {!hasThreshold && <span style={{ fontSize: 11, marginLeft: 4 }}>(default)</span>}
                </span>
              </div>
              <Button
                icon={<FilePdfOutlined />}
                size="small"
                onClick={handleExportPdf}
                loading={exportingPdf}
                disabled={qualified.length === 0}
                style={{ flexShrink: 0 }}
              >
                Export PDF
              </Button>
            </div>

            {isLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : qualified.length === 0 ? (
              <div style={{ padding: '24px 0', textAlign: 'center', color: '#64648a', fontSize: 14 }}>
                No candidates meet the threshold yet.
              </div>
            ) : (
              <Table<QualEntry>
                columns={qualColumns}
                dataSource={qualified}
                rowKey="candidate_id"
                size="small"
                pagination={{ pageSize: 20, hideOnSinglePage: true, showSizeChanger: false }}
                onRow={record => ({
                  onClick: () => setSelectedCandidate(record),
                  style: { cursor: 'pointer' },
                })}
              />
            )}
          </div>
        </div>

        {/* Right: Insight Panel */}
        <div className="data-panel ra-insight-panel">
          <div className="ra-insight-header">
            <span className="ra-section-title">Insight Panel</span>
            <Tooltip title="Pipeline health based on qualified candidates vs. interview target.">
              <InfoCircleOutlined style={{ color: '#64648a', fontSize: 15, cursor: 'pointer' }} />
            </Tooltip>
          </div>

          {isLoading ? (
            <Skeleton active paragraph={{ rows: 8 }} style={{ padding: '0 4px' }} />
          ) : (
            <>
              <div className="ra-insight-section">
                <div className="ra-insight-section-label">Pipeline Status</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 10 }}>
                  <div className="ra-status-icon" style={{ background: `${status.color}22`, border: `1px solid ${status.color}44` }}>
                    <BarChartOutlined style={{ fontSize: 20, color: status.color }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 800, color: status.color, lineHeight: 1.2 }}>
                      {status.label}
                    </div>
                    <div style={{ fontSize: 12, color: '#64648a', marginTop: 3 }}>
                      {Math.round(fillPct)}% of interview target met
                    </div>
                  </div>
                </div>
              </div>

              <div className="ra-insight-divider" />

              <div className="ra-insight-section">
                <div className="ra-insight-section-label">What this means</div>
                <p style={{ fontSize: 13, color: '#a1a1bb', lineHeight: 1.55, margin: '8px 0 0' }}>
                  {status.description}
                </p>
              </div>

              <div className="ra-insight-divider" />

              <div className="ra-insight-section">
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div className="ra-status-icon" style={{ background: 'rgba(91,106,245,0.12)', border: '1px solid rgba(91,106,245,0.25)' }}>
                    <TeamOutlined style={{ fontSize: 20, color: '#5b6af5' }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: '#a1a1bb' }}>How many are missing?</div>
                    <div style={{ fontSize: 28, fontWeight: 800, fontFamily: 'Fira Code, monospace', color: '#5b6af5', lineHeight: 1.15 }}>
                      {missing}
                    </div>
                    <div style={{ fontSize: 12, color: '#64648a', marginTop: 2 }}>
                      {missing === 0
                        ? 'Target reached — pipeline is full.'
                        : `more qualified candidates needed to reach the target of ${target}.`}
                    </div>
                  </div>
                </div>
              </div>

              <div className="ra-insight-divider" />

              <div className="ra-insight-section">
                <div className="ra-insight-section-label">At a glance</div>
                <ul className="ra-at-glance">
                  <li>
                    <span className="ra-glance-key">Qualified:</span>
                    <span className="ra-glance-val">{qualified.length}</span>
                  </li>
                  <li>
                    <span className="ra-glance-key">Target:</span>
                    <span className="ra-glance-val">{target}{!hasTarget && <span style={{ fontSize: 10, color: '#64648a', fontFamily: 'inherit', fontWeight: 400 }}> (default)</span>}</span>
                  </li>
                  <li>
                    <span className="ra-glance-key">Threshold:</span>
                    <span className="ra-glance-val">{threshold.toFixed(1)} / 10{!hasThreshold && <span style={{ fontSize: 10, color: '#64648a', fontFamily: 'inherit', fontWeight: 400 }}> (default)</span>}</span>
                  </li>
                  <li>
                    <span className="ra-glance-key">Progress:</span>
                    <span className="ra-glance-val">{Math.round(fillPct)}%</span>
                  </li>
                  {totalApplications > 0 && (
                    <li>
                      <span className="ra-glance-key">Total applicants:</span>
                      <span className="ra-glance-val">{totalApplications}</span>
                    </li>
                  )}
                  {unscoredCount > 0 && (
                    <li>
                      <span className="ra-glance-key">Awaiting scoring:</span>
                      <span className="ra-glance-val" style={{ color: '#fbbf24' }}>{unscoredCount}</span>
                    </li>
                  )}
                </ul>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── Score Reasoning Drawer ────────────────────────────────────────────── */}
      <Drawer
        title={
          selectedCandidate && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontWeight: 700 }}>{selectedCandidate.candidate_name || 'Candidate'}</span>
              {selectedCandidate.display != null && (
                <span style={{
                  fontFamily: 'Fira Code, monospace',
                  fontWeight: 800,
                  fontSize: 18,
                  color: '#34d399',
                }}>
                  {selectedCandidate.display.toFixed(1)}
                </span>
              )}
            </div>
          )
        }
        open={selectedCandidate != null}
        onClose={() => setSelectedCandidate(null)}
        width={440}
      >
        {selectedCandidate && (
          <>
            {/* Score header */}
            <div style={{ textAlign: 'center', marginBottom: 28, padding: '16px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ fontSize: 56, fontWeight: 800, color: '#34d399', fontFamily: 'Fira Code, monospace', lineHeight: 1 }}>
                {selectedCandidate.display?.toFixed(1)}
              </div>
              <div style={{ fontSize: 13, color: '#64648a', marginTop: 6 }}>out of 10</div>
              {selectedCandidate.candidate_email && (
                <div style={{ fontSize: 12, color: '#64648a', marginTop: 4 }}>
                  {selectedCandidate.candidate_email}
                </div>
              )}
              {selectedCandidate.candidate_seniority && (
                <Tag style={{ marginTop: 8, fontSize: 11 }}>{selectedCandidate.candidate_seniority}</Tag>
              )}
            </div>

            {/* Dimension breakdown */}
            {Object.keys(selectedCandidate.dimension_scores).length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <div style={{ fontSize: 11, fontWeight: 800, color: '#64648a', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 14 }}>
                  Score Breakdown
                </div>
                {Object.entries(selectedCandidate.dimension_scores).map(([key, val]) => {
                  const displayVal = Math.round(val) / 10;
                  const pct = Math.min(100, val);
                  return (
                    <div key={key} style={{ marginBottom: 14 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, fontSize: 13 }}>
                        <span style={{ color: '#a1a1bb', textTransform: 'capitalize' }}>
                          {key.replace(/_/g, ' ')}
                        </span>
                        <span style={{ fontFamily: 'Fira Code, monospace', fontWeight: 700, color: '#ededf5', fontSize: 13 }}>
                          {displayVal.toFixed(1)}
                        </span>
                      </div>
                      <div style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.08)' }}>
                        <div style={{
                          height: '100%',
                          width: `${pct}%`,
                          borderRadius: 'inherit',
                          background: displayVal >= (hasThreshold ? threshold : 7.5)
                            ? 'linear-gradient(90deg, #5b6af5, #7b8aff)'
                            : 'rgba(91,106,245,0.4)',
                          transition: 'width 400ms ease',
                        }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Reasoning text */}
            {selectedCandidate.reasoning ? (
              <div>
                <div style={{ fontSize: 11, fontWeight: 800, color: '#64648a', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                  AI Reasoning
                </div>
                <p style={{ fontSize: 13, color: '#a1a1bb', lineHeight: 1.7, margin: 0, whiteSpace: 'pre-wrap' }}>
                  {selectedCandidate.reasoning}
                </p>
              </div>
            ) : (
              <div style={{ color: '#64648a', fontSize: 13, fontStyle: 'italic' }}>
                No reasoning available for this score.
              </div>
            )}

            {/* Navigate to full profile */}
            <div style={{ marginTop: 28, paddingTop: 20, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
              <Button
                type="default"
                block
                onClick={() => navigate(`/candidates/${selectedCandidate.candidate_id}`)}
              >
                View Full Profile
              </Button>
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}
