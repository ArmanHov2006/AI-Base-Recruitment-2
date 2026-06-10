import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Empty, InputNumber, Tag, Tooltip } from 'antd';
import { ArrowLeftOutlined, UserOutlined, SwapOutlined } from '@ant-design/icons';

import { getJob, getJobShortlist } from '../api/jobs';
import ScoreRadar from '../components/ScoreRadar';
import type { ShortlistEntry, Tier } from '../types';

const seniorityColorMap: Record<string, string> = {
  junior: 'green',
  mid: 'blue',
  senior: 'orange',
  lead: 'purple',
};

const DIM_LABELS: Record<string, string> = {
  skills_match: 'Skills',
  experience_level: 'Experience',
  education: 'Education',
  seniority_fit: 'Seniority',
};

const TIER_META: Record<Tier, { label: string; accent: string; bg: string; border: string }> = {
  S: { label: 'S - Clear advance',          accent: '#22c55e', bg: 'rgba(34,197,94,0.06)',   border: '#22c55e' },
  A: { label: 'A - Contested (you decide)', accent: '#fbbf24', bg: 'rgba(251,191,36,0.06)',  border: '#fbbf24' },
  B: { label: 'B - Qualified backup',       accent: '#5b6af5', bg: 'rgba(91,106,245,0.05)',  border: '#5b6af5' },
  F: { label: 'F - Below threshold',        accent: '#6b7280', bg: 'rgba(107,114,128,0.04)', border: '#6b7280' },
};

function TierChip({ tier }: { tier: Tier | null }) {
  if (!tier) return null;
  const m = TIER_META[tier];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 7px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 700,
        fontFamily: "'Fira Code', monospace",
        letterSpacing: '0.04em',
        color: m.accent,
        background: m.bg,
        border: `1px solid ${m.accent}33`,
      }}
    >
      {tier}
    </span>
  );
}

function EntryRow({ entry, rowIndex = 0 }: { entry: ShortlistEntry; rowIndex?: number }) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const dims = entry.dimension_scores;
  const tierMeta = entry.tier ? TIER_META[entry.tier] : null;
  const scoreColor =
    entry.tier === 'S' ? '#22c55e'
    : entry.tier === 'A' ? '#fbbf24'
    : entry.tier === 'B' ? '#5b6af5'
    : '#6b7280';
  const barColor = scoreColor;

  return (
    <div
      className="leaderboard-row-wrap"
      style={{
        '--row-index': rowIndex,
        '--tier-bar-color': barColor,
        ...(tierMeta ? { background: tierMeta.bg } : {}),
      } as React.CSSProperties}
    >
      <div
        className={`leaderboard-row${entry.rank === 1 ? ' is-first' : ''}`}
        style={tierMeta ? { borderLeftColor: tierMeta.border } : undefined}
      >
        {/* Rank + tier chip */}
        <div className="lb-rank-cell">
          <span className={`rank-badge${entry.rank <= 3 ? ` rank-${entry.rank}` : ''}`}>#{entry.rank}</span>
          <TierChip tier={entry.tier} />
        </div>

        {/* Candidate */}
        <div className="lb-candidate-cell">
          <div className="lb-candidate-name">{entry.candidate_name || 'Unknown'}</div>
          {entry.candidate_seniority && (
            <div className="lb-candidate-seniority">
              <Tag
                color={seniorityColorMap[entry.candidate_seniority.toLowerCase()] || 'default'}
                style={{ margin: 0, fontSize: 11 }}
              >
                {entry.candidate_seniority}
              </Tag>
            </div>
          )}
          {entry.candidate_email && (
            <div className="lb-email">{entry.candidate_email}</div>
          )}
        </div>

        {/* Score */}
        <div className="lb-score-cell">
          <span
            className="lb-score-pill"
            style={{
              background: `${scoreColor}14`,
              borderColor: `${scoreColor}30`,
            }}
          >
            <span className="lb-score-num" style={{ color: scoreColor }}>
              {entry.overall_score_10 != null ? entry.overall_score_10.toFixed(1) : '--'}
            </span>
            <span className="lb-score-unit">/10</span>
          </span>
        </div>

        {/* Scored date */}
        <div>
          {entry.scored_at ? (
            <Tooltip title={new Date(entry.scored_at).toLocaleString()}>
              <span className="lb-date">{new Date(entry.scored_at).toLocaleDateString()}</span>
            </Tooltip>
          ) : (
            <span style={{ color: '#64648a' }}>--</span>
          )}
        </div>

        {/* Dimension preview bars */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {Object.entries(dims).slice(0, 2).map(([key, val]) => (
            <div key={key} className="lb-dim-row">
              <span className="lb-dim-label">{DIM_LABELS[key] ?? key.replace(/_/g, ' ')}</span>
              <div className="dimension-track" style={{ flex: 1 }}>
                <div className="dimension-fill" style={{ width: `${val}%` }} />
              </div>
              <span className="lb-dim-val">{val}</span>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="lb-actions-cell">
          <Button
            size="small"
            icon={<UserOutlined />}
            onClick={() => navigate(`/candidates/${entry.candidate_id}`)}
            aria-label="View candidate profile"
          />
          <button
            className="lb-expand-btn"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? 'Collapse details' : 'Expand details'}
            aria-expanded={expanded}
          >
            <span className={`lb-chevron${expanded ? ' is-open' : ''}`}>›</span>
          </button>
        </div>
      </div>

      {/* Smooth expand panel via CSS grid trick */}
      <div className={`lb-expand-wrap${expanded ? ' is-open' : ''}`} aria-hidden={!expanded}>
        <div className="lb-expand-inner">
          <div className="leaderboard-details">
            <div>
              <div className="dense-label" style={{ marginBottom: 10 }}>Score anatomy</div>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
                <ScoreRadar scores={dims} />
              </div>
              <div className="dimension-list">
                {Object.entries(dims).map(([key, val]) => (
                  <div key={key} className="dimension-row">
                    <span>{DIM_LABELS[key] ?? key.replace(/_/g, ' ')}</span>
                    <div className="dimension-track">
                      <div className="dimension-fill" style={{ width: `${val}%` }} />
                    </div>
                    <span style={{ fontFamily: "'Fira Code', monospace", fontSize: 12 }}>{val}</span>
                  </div>
                ))}
              </div>
            </div>

            {(entry.skill_breakdown?.technical?.length ?? 0) > 0 && (
              <div>
                <div className="dense-label" style={{ marginBottom: 10 }}>Technical skills</div>
                <div className="dimension-list">
                  {entry.skill_breakdown!.technical.slice(0, 6).map((s) => (
                    <div key={s.name} className="dimension-row">
                      <span>{s.name}</span>
                      <div className="dimension-track">
                        <div className="dimension-fill" style={{ width: `${s.score}%` }} />
                      </div>
                      <span style={{ fontFamily: "'Fira Code', monospace", fontSize: 12 }}>{s.score}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              {entry.reasoning && (
                <>
                  <div className="dense-label" style={{ marginBottom: 8 }}>Reasoning</div>
                  <p style={{ fontSize: 13, color: '#a1a1bb', lineHeight: 1.55, margin: '0 0 12px' }}>
                    {entry.reasoning.slice(0, 300)}{entry.reasoning.length > 300 ? '…' : ''}
                  </p>
                </>
              )}
              <Button
                type="link"
                size="small"
                onClick={() => navigate(`/candidates/${entry.candidate_id}`)}
                style={{ paddingLeft: 0 }}
              >
                View full profile
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const COMPARE_MAX = 20;

function TierSection({
  tier,
  entries,
  collapsible,
  jobId,
  slotsRemaining,
}: {
  tier: Tier | null;
  entries: ShortlistEntry[];
  collapsible?: boolean;
  jobId?: string;
  slotsRemaining?: number;
}) {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(collapsible ?? false);
  if (entries.length === 0) return null;

  const meta = tier ? TIER_META[tier] : null;
  const sectionLabel = meta ? meta.label : 'Qualified';
  const comparableEntries = entries.filter((e) => e.tier !== 'F');
  const canCompare = tier === 'A' && jobId && comparableEntries.length >= 2;
  const compareCount = Math.min(comparableEntries.length, COMPARE_MAX);

  function handleCompareAll() {
    if (!jobId) return;
    const ids = comparableEntries.slice(0, COMPARE_MAX).map((e) => e.candidate_id);
    const params = new URLSearchParams({ candidates: ids.join(',') });
    if (slotsRemaining != null && slotsRemaining > 0) params.set('slots', String(slotsRemaining));
    navigate(`/jobs/${jobId}/compare?${params.toString()}`);
  }

  return (
    <div className="lb-tier-section">
      <div
        className={`lb-tier-head${collapsible ? ' is-collapsible' : ''}`}
        style={
          meta
            ? { background: meta.bg, borderColor: `${meta.accent}22`, color: meta.accent }
            : { background: 'rgba(91,106,245,0.04)', color: '#5b6af5' }
        }
        onClick={collapsible ? () => setCollapsed((v) => !v) : undefined}
      >
        <div className="lb-tier-identity">
          {tier && (
            <span
              className="lb-tier-badge"
              style={{
                color: meta!.accent,
                borderColor: `${meta!.accent}55`,
                background: `${meta!.accent}14`,
              }}
            >
              {tier}
            </span>
          )}
          <div className="lb-tier-text">
            <div className="lb-tier-label">{sectionLabel}</div>
            <div className="lb-tier-count">
              {entries.length} candidate{entries.length !== 1 ? 's' : ''}
            </div>
          </div>
        </div>

        {canCompare && (
          <Tooltip title={`Compare all ${compareCount} contested candidates — AI ranks them and highlights the best ${slotsRemaining ?? 1} to advance`}>
            <Button
              size="small"
              icon={<SwapOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleCompareAll();
              }}
              style={{ fontSize: 11, marginLeft: 4 }}
            >
              Compare all {compareCount}
            </Button>
          </Tooltip>
        )}

        <span style={{ marginLeft: 'auto' }} />

        {collapsible && (
          <span className={`lb-tier-toggle${collapsed ? ' is-collapsed' : ''}`}>▼</span>
        )}

        {tier && (
          <span className="lb-tier-ghost" aria-hidden="true">
            {tier}
          </span>
        )}
      </div>

      {!collapsed &&
        entries.map((e, i) => <EntryRow key={e.candidate_id} entry={e} rowIndex={i} />)}
    </div>
  );
}

export default function Leaderboard() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    retry: false,
  });

  const [targetInput, setTargetInput] = useState<number | null>(null);
  const [thresholdInput, setThresholdInput] = useState<number | null>(null);

  const effectiveTarget = targetInput ?? job?.candidates_for_next_stage ?? null;
  const effectiveThreshold = thresholdInput ?? job?.threshold_score ?? 7.5;

  const { data: shortlist, isLoading: shortlistLoading } = useQuery({
    queryKey: ['shortlist', jobId, effectiveTarget, effectiveThreshold],
    queryFn: () => getJobShortlist(jobId!, effectiveTarget, effectiveThreshold),
    enabled: !!jobId,
    staleTime: 30_000,
  });

  if (jobLoading) {
    return (
      <div className="leaderboard-skeleton">
        {[0, 1, 2, 3].map((i) => (
          <div className="leaderboard-skeleton-row" key={i} />
        ))}
      </div>
    );
  }

  if (!job) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <p style={{ color: '#a1a1bb' }}>Job not found</p>
        <Button onClick={() => navigate('/jobs')}>Back to Jobs</Button>
      </div>
    );
  }

  const entries = shortlist?.entries ?? [];
  const mode = shortlist?.mode ?? 'qualified_only';

  const grouped: Record<string, ShortlistEntry[]> = {
    S: [], A: [], B: [], F: [], qualified: [], out: [],
  };
  for (const e of entries) {
    if (mode === 'qualified_only') {
      if (e.tier === 'F') grouped.out.push(e);
      else grouped.qualified.push(e);
    } else {
      if (e.tier && e.tier in grouped) grouped[e.tier].push(e);
      else grouped.out.push(e);
    }
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14, fontSize: 13, color: '#64648a' }}>
        <span
          role="link"
          tabIndex={0}
          style={{ cursor: 'pointer', color: 'var(--color-primary)', fontWeight: 500 }}
          onClick={() => navigate('/jobs')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') navigate('/jobs'); }}
        >
          Jobs
        </span>
        <span>/</span>
        <span
          role="link"
          tabIndex={0}
          style={{ cursor: 'pointer', color: 'var(--color-primary)', fontWeight: 500 }}
          onClick={() => navigate(`/jobs/${jobId}`)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') navigate(`/jobs/${jobId}`); }}
        >
          {job.title}
        </span>
        <span>/</span>
        <span style={{ color: '#a1a1bb', fontWeight: 600 }} aria-current="page">Shortlist</span>
      </div>

      {/* Page header */}
      <div className="lb-page-header">
        <Button
          shape="circle"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(`/jobs/${jobId}`)}
          aria-label="Back to job"
        />
        <div>
          <h1 className="lb-page-title">Candidate Shortlist</h1>
          <p className="lb-page-sub">{job.title}</p>
        </div>
      </div>

      {/* Controls */}
      <div className="lb-controls">
        <div className="lb-controls-group">
          <span className="lb-controls-label">Advance target</span>
          <InputNumber
            value={effectiveTarget}
            onChange={(v) => setTargetInput(v ?? null)}
            min={1}
            max={9999}
            placeholder="--"
            style={{ width: 80 }}
            size="small"
          />
        </div>
        <div className="lb-controls-group">
          <span className="lb-controls-label">Threshold</span>
          <InputNumber
            value={effectiveThreshold}
            onChange={(v) => setThresholdInput(v ?? null)}
            min={0}
            max={10}
            step={0.5}
            placeholder="7.5"
            style={{ width: 80 }}
            size="small"
          />
          <span style={{ fontSize: 11, color: '#64648a' }}>/10</span>
        </div>
        {(job.candidates_for_next_stage != null || job.threshold_score != null) && (
          <Button
            size="small"
            type="text"
            onClick={() => { setTargetInput(null); setThresholdInput(null); }}
            style={{ fontSize: 12, color: '#5b6af5' }}
          >
            Reset defaults
          </Button>
        )}
        {shortlist && (
          <div className="lb-controls-stats">
            <div className="lb-stat">
              <span className="lb-stat-val">{shortlist.scored_count}</span>
              <span className="lb-stat-label">Scored</span>
            </div>
            <div className="lb-stat">
              <span className="lb-stat-val">{shortlist.applicant_count}</span>
              <span className="lb-stat-label">Total</span>
            </div>
            {shortlist.cut_rating != null && (
              <div className="lb-stat">
                <span className="lb-stat-val">{shortlist.cut_rating.toFixed(1)}</span>
                <span className="lb-stat-label">Cut</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Board */}
      {!shortlistLoading && entries.length === 0 ? (
        <div className="data-panel" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <Empty
            description={
              <span style={{ color: '#a1a1bb' }}>
                No candidates scored yet. Upload resumes and run a comparison first.
              </span>
            }
          >
            <Button type="primary" onClick={() => navigate(`/jobs/${jobId}`)}>
              Back to job
            </Button>
          </Empty>
        </div>
      ) : shortlistLoading ? (
        <div className="leaderboard-skeleton">
          {[0, 1, 2].map((i) => (
            <div className="leaderboard-skeleton-row" key={i} />
          ))}
        </div>
      ) : mode === 'qualified_only' ? (
        <div>
          <div className="lb-unlock-hint">
            Set an advance target above to unlock S / A / B tier grouping.
          </div>
          <div className="leaderboard-panel">
            <div className="leaderboard-head">
              <div>#</div>
              <div>Candidate</div>
              <div>Score</div>
              <div>Scored</div>
              <div>Dimensions</div>
              <div />
            </div>
            <TierSection tier={null} entries={grouped.qualified} jobId={jobId} />
            <TierSection tier="F" entries={grouped.out} collapsible jobId={jobId} />
          </div>
        </div>
      ) : (
        <div className="leaderboard-panel">
          <div className="leaderboard-head">
            <div>#</div>
            <div>Candidate</div>
            <div>Score</div>
            <div>Scored</div>
            <div>Dimensions</div>
            <div />
          </div>
          <TierSection tier="S" entries={grouped.S} jobId={jobId} />
          <TierSection
            tier="A"
            entries={grouped.A}
            jobId={jobId}
            slotsRemaining={
              effectiveTarget != null
                ? Math.max(1, effectiveTarget - grouped.S.length)
                : undefined
            }
          />
          <TierSection tier="B" entries={grouped.B} jobId={jobId} />
          <TierSection tier="F" entries={grouped.F} collapsible jobId={jobId} />
        </div>
      )}
    </div>
  );
}
