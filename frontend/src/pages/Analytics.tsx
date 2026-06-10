import { useEffect, useRef, useState } from 'react';
import { Skeleton } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getAnalyticsOverview, getAnalyticsFunnel, getCandidateSources } from '../api/analytics';
import { searchCandidates } from '../api/candidates';
import type { CandidateResponse } from '../types';

const STAGE_LABELS: Record<string, string> = {
  applied: 'Applied',
  reviewing: 'Reviewing',
  shortlisted: 'Shortlisted',
  interview: 'Interview',
  offer: 'Offer',
  hired: 'Hired',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  parsing: 'Parsing',
  screening: 'Screening',
};

const AVATAR_PALETTE = [
  '#3d4acc', '#10b981', '#7c3aed', '#d97706', '#e11d48',
  '#0891b2', '#c2410c', '#15803d',
];

function avatarBg(id: string): string {
  const sum = id.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return AVATAR_PALETTE[sum % AVATAR_PALETTE.length];
}

function initials(name?: string | null): string {
  if (!name) return 'C';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map(p => p[0]?.toUpperCase()).join('');
}

function scoreColor(s?: number | null): string {
  if (s == null) return '#64648a';
  if (s >= 80) return '#34d399';
  if (s >= 60) return '#fbbf24';
  return '#f87171';
}

function timeAgo(iso?: string | null): string {
  if (!iso) return '';
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function useCountUp(target: number, duration = 700): number {
  const [val, setVal] = useState(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (target === 0) { setVal(0); return; }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(Math.round(eased * target));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return val;
}

interface KpiTileProps {
  label: string;
  value: number;
  suffix?: string;
  loading: boolean;
  delay?: number;
  variant?: '' | 'tile-positive' | 'tile-attention' | 'tile-neutral';
}

function KpiTile({ label, value, suffix = '', loading, delay = 0, variant = '' }: KpiTileProps) {
  const animated = useCountUp(loading ? 0 : value);
  return (
    <div className={`metric-tile ${variant}`.trim()} style={{ animationDelay: `${delay}ms` }}>
      <span>{label}</span>
      <strong>
        {loading ? '—' : `${animated}${suffix}`}
      </strong>
    </div>
  );
}

// Semantic color per application status — used by the By Status panel.
const STATUS_COLOR: Record<string, string> = {
  applied: '#5b6af5',
  reviewing: '#a78bfa',
  screening: '#a78bfa',
  shortlisted: '#34d399',
  interview: '#38bdf8',
  offer: '#fbbf24',
  hired: '#34d399',
  rejected: '#f87171',
  withdrawn: '#64648a',
};
function statusColor(status: string): string {
  return STATUS_COLOR[status] || '#64648a';
}

function CandidateRowSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', padding: '8px 16px', gap: 0 }}>
      {[0, 1, 2, 3, 4, 5].map(i => (
        <div
          key={i}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 0',
            borderBottom: i < 5 ? '1px solid rgba(255,255,255,0.05)' : 'none',
          }}
        >
          <div style={{ width: 34, height: 34, borderRadius: 9, background: 'rgba(255,255,255,0.06)', flexShrink: 0 }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ height: 11, width: `${55 + i * 7}%`, borderRadius: 4, background: 'rgba(255,255,255,0.06)', position: 'relative', overflow: 'hidden' }}
              className="skeleton-row" />
            <div style={{ height: 9, width: `${35 + i * 5}%`, borderRadius: 4, background: 'rgba(255,255,255,0.04)' }} />
          </div>
          <div style={{ width: 28, height: 16, borderRadius: 4, background: 'rgba(255,255,255,0.05)' }} />
        </div>
      ))}
    </div>
  );
}

export default function Analytics() {
  const navigate = useNavigate();

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['analytics', 'overview'],
    queryFn: getAnalyticsOverview,
  });

  const { data: funnel, isLoading: funnelLoading } = useQuery({
    queryKey: ['analytics', 'funnel'],
    queryFn: () => getAnalyticsFunnel(),
  });

  const { data: recentData, isLoading: candidatesLoading } = useQuery({
    queryKey: ['candidates', 'recent-overview'],
    queryFn: () => searchCandidates({ page: 1, size: 8 }),
  });

  const { data: sourcesData, isLoading: sourcesLoading } = useQuery({
    queryKey: ['analytics', 'sources'],
    queryFn: getCandidateSources,
  });

  const recentCandidates: CandidateResponse[] = recentData?.items ?? [];
  const topSkills = overview?.top_skills ?? [];
  const sources = sourcesData?.data ?? [];

  // Distinct candidates with an in-flight application (counts people, not
  // applications) so the ACTIVE tile can never exceed total candidates.
  const activeCount = overview?.active_candidates ?? 0;

  const hiredCount = overview?.applications_by_status?.hired ?? 0;

  const funnelStages = (funnel?.stages ?? []).slice(0, 5);
  const maxFunnelCount = funnelStages.length > 0 ? Math.max(...funnelStages.map(s => s.count)) : 1;

  return (
    <div className="page-shell">
      {/* KPI strip — 4 tiles */}
      <div className="metric-strip">
        <KpiTile label="CANDIDATES" value={overview?.total_candidates ?? 0} loading={overviewLoading} delay={0} />
        <KpiTile label="ACTIVE" value={activeCount} loading={overviewLoading} delay={50} variant="tile-attention" />
        <KpiTile label="OPEN JOBS" value={overview?.total_jobs ?? 0} loading={overviewLoading} delay={100} variant="tile-neutral" />
        <KpiTile label="HIRED" value={hiredCount} loading={overviewLoading} delay={150} variant="tile-positive" />
      </div>

      {/* Main 2-column layout */}
      <div className="overview-grid">
        {/* Left — Recent candidates */}
        <div className="data-panel overview-candidates-panel">
          <div className="data-panel-header">
            <h2>Recent Candidates</h2>
            <button
              type="button"
              className="overview-see-all"
              onClick={() => navigate('/')}
            >
              See all →
            </button>
          </div>

          {candidatesLoading ? (
            <CandidateRowSkeleton />
          ) : (
            <div className="overview-candidate-list">
              {recentCandidates.map((c, i) => (
                <div
                  key={c.id}
                  className="overview-candidate-row"
                  style={{ animationDelay: `${80 + i * 40}ms` }}
                  onClick={() => navigate(`/candidates/${c.id}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && navigate(`/candidates/${c.id}`)}
                  aria-label={`View ${c.name || 'candidate'}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
                    <div className="overview-avatar" style={{ background: avatarBg(c.id) }}>
                      {initials(c.name || c.email)}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div className="overview-cname">{c.name || 'Unnamed'}</div>
                      <div className="overview-csub">
                        {c.desired_position || c.seniority || '—'}
                        {c.location ? ` · ${c.location}` : ''}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
                    <span style={{ color: '#64648a', fontSize: 11 }}>{timeAgo(c.created_at)}</span>
                    {(c as CandidateResponse & { fit_score?: number }).fit_score != null && (
                      <span
                        className="overview-score"
                        style={{ color: scoreColor((c as CandidateResponse & { fit_score?: number }).fit_score) }}
                      >
                        {(c as CandidateResponse & { fit_score?: number }).fit_score}
                      </span>
                    )}
                  </div>
                </div>
              ))}

              {recentCandidates.length === 0 && (
                <div style={{ padding: '36px 16px', textAlign: 'center', color: '#64648a', fontSize: 14 }}>
                  No candidates yet — upload your first resume to get started.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right column */}
        <div className="overview-right-col">
          {/* AI Insights panel — indigo accent */}
          <div className="data-panel overview-ai-panel">
            <div className="overview-ai-accent" />
            <div className="data-panel-header" style={{ borderBottom: '1px solid rgba(91,106,245,0.15)' }}>
              <h2 style={{ color: '#a0aaff' }}>AI Insights</h2>
              <span
                style={{
                  color: '#5b6af5',
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  border: '1px solid rgba(91,106,245,0.3)',
                  borderRadius: 4,
                  padding: '2px 7px',
                  background: 'rgba(91,106,245,0.08)',
                }}
              >
                Live
              </span>
            </div>

            <div style={{ padding: '14px 16px' }}>
              {overviewLoading ? (
                <Skeleton active paragraph={{ rows: 4 }} />
              ) : (
                <>
                  {topSkills.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div style={{
                        color: '#64648a',
                        fontSize: 11,
                        fontWeight: 800,
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        marginBottom: 10,
                      }}>
                        Top Demanded Skills
                      </div>
                      {topSkills.slice(0, 4).map((s, i) => {
                        const maxCount = topSkills[0]?.count || 1;
                        const pct = Math.round((s.count / maxCount) * 100);
                        return (
                          <div
                            key={s.skill}
                            className="ai-skill-row"
                            style={{ animationDelay: `${120 + i * 50}ms` }}
                          >
                            <span style={{ color: '#a1a1bb', fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {s.skill}
                            </span>
                            <div style={{ width: 72, height: 4, borderRadius: 999, background: 'rgba(255,255,255,0.07)', overflow: 'hidden', flexShrink: 0 }}>
                              <div style={{
                                width: `${pct}%`,
                                height: '100%',
                                background: 'var(--color-primary)',
                                borderRadius: 'inherit',
                                transition: `width ${500 + i * 80}ms ease-out`,
                              }} />
                            </div>
                            <span style={{ color: '#64648a', fontSize: 11, width: 26, textAlign: 'right', fontFamily: 'Fira Code, monospace' }}>
                              {s.count}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="ai-stat-row">
                    <span>Applications</span>
                    <strong>{overview?.total_applications ?? 0}</strong>
                  </div>
                  <div className="ai-stat-row">
                    <span>Hire Rate</span>
                    <strong style={{ color: hiredCount > 0 ? '#34d399' : 'var(--color-muted)' }}>
                      {overview?.total_applications
                        ? `${Math.round((hiredCount / overview.total_applications) * 100)}%`
                        : '—'}
                    </strong>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Pipeline mini-funnel */}
          <div className="data-panel overview-funnel-panel">
            <div className="data-panel-header">
              <h2>Pipeline</h2>
              <span>{funnel?.stages.reduce((a, s) => a + s.count, 0) ?? 0} total</span>
            </div>
            <div style={{ padding: '12px 16px' }}>
              {funnelLoading ? (
                <Skeleton active paragraph={{ rows: 4 }} />
              ) : funnelStages.length === 0 ? (
                <div style={{ padding: '20px 0', textAlign: 'center', color: '#64648a', fontSize: 13 }}>
                  No pipeline data
                </div>
              ) : (
                funnelStages.map((stage, i) => {
                  const pct = maxFunnelCount > 0 ? Math.round((stage.count / maxFunnelCount) * 100) : 0;
                  return (
                    <div key={stage.stage} style={{ marginBottom: i < funnelStages.length - 1 ? 10 : 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ color: '#a1a1bb', fontSize: 12 }}>
                          {STAGE_LABELS[stage.stage] || stage.stage}
                        </span>
                        <span style={{ color: '#ededf5', fontSize: 12, fontFamily: 'Fira Code, monospace', fontWeight: 700 }}>
                          {stage.count}
                        </span>
                      </div>
                      <div className="bar-track" style={{ height: 5 }}>
                        <div
                          className="bar-fill"
                          style={{
                            width: `${pct}%`,
                            background: statusColor(stage.stage),
                            transition: `width ${500 + i * 60}ms ease-out`,
                          }}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom row — skills + status */}
      <div className="overview-bottom-row">
        <div className="data-panel" style={{ flex: '1 1 0' }}>
          <div className="data-panel-header">
            <h2>Top Skills</h2>
            <span>{topSkills.length} tracked</span>
          </div>
          <div style={{ padding: '14px 16px' }}>
            {overviewLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : topSkills.length === 0 ? (
              <div style={{ padding: '16px 0', color: '#64648a', fontSize: 13 }}>No skill data yet</div>
            ) : (
              topSkills.slice(0, 6).map(s => {
                const maxCount = topSkills[0]?.count || 1;
                const pct = Math.round((s.count / maxCount) * 100);
                return (
                  <div key={s.skill} className="skill-bar">
                    <div className="skill-bar-meta">
                      <span className="skill-bar-name">{s.skill}</span>
                      <span className="skill-bar-count">{s.count}</span>
                    </div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="data-panel" style={{ flex: '1 1 0' }}>
          <div className="data-panel-header">
            <h2>By Status</h2>
            <span>{overview?.total_applications ?? 0} total</span>
          </div>
          <div style={{ padding: '14px 16px' }}>
            {overviewLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : Object.keys(overview?.applications_by_status ?? {}).length === 0 ? (
              <div style={{ padding: '16px 0', color: '#64648a', fontSize: 13 }}>No application data yet</div>
            ) : (
              (() => {
                const rows = Object.entries(overview?.applications_by_status ?? {})
                  .filter(([, v]) => v > 0)
                  .slice(0, 7);
                const maxCount = rows.length > 0 ? Math.max(...rows.map(([, v]) => v)) : 1;
                return rows.map(([status, count], i) => {
                  const color = statusColor(status);
                  const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
                  return (
                    <div key={status} className="status-row">
                      <div className="status-row-left">
                        <span className="status-dot" style={{ background: color }} />
                        <span style={{ color: '#a1a1bb', fontSize: 13, flexShrink: 0, minWidth: 78 }}>
                          {STAGE_LABELS[status] || status}
                        </span>
                        <div className="status-bar-track">
                          <div
                            className="status-bar-fill"
                            style={{ width: `${pct}%`, background: color, animationDelay: `${i * 50}ms` }}
                          />
                        </div>
                      </div>
                      <strong style={{ fontFamily: 'Fira Code, monospace', fontSize: 15, color }}>
                        {count}
                      </strong>
                    </div>
                  );
                });
              })()
            )}
          </div>
        </div>

        <div className="data-panel" style={{ flex: '1 1 0' }}>
          <div className="data-panel-header">
            <h2>By Source</h2>
            <span>{sources.length} channels</span>
          </div>
          <div style={{ padding: '14px 16px' }}>
            {sourcesLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : sources.length === 0 ? (
              <div style={{ padding: '16px 0', color: '#64648a', fontSize: 13 }}>No source data yet</div>
            ) : (
              (() => {
                const maxCount = sources[0]?.count || 1;
                return sources.slice(0, 8).map((s, i) => {
                  const pct = Math.round((s.count / maxCount) * 100);
                  return (
                    <div key={s.source} className="skill-bar" style={{ animationDelay: `${i * 40}ms` }}>
                      <div className="skill-bar-meta">
                        <span className="skill-bar-name" style={{ textTransform: 'capitalize' }}>
                          {s.source}
                        </span>
                        <span className="skill-bar-count">{s.count}</span>
                      </div>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{ width: `${pct}%`, transition: `width ${500 + i * 60}ms ease-out` }}
                        />
                      </div>
                    </div>
                  );
                });
              })()
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
