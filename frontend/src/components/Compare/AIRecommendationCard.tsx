import { Button } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ProfileOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StarOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import type { ComparisonVerdict, ComparisonResultResponse, CandidateResponse } from '../../types';
import { SENIORITY_CONFIG } from '../../constants/seniority';

interface Props {
  verdict: ComparisonVerdict | null;
  analysis: string | null;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  results: ComparisonResultResponse[];
  candidatesMap: Map<string, CandidateResponse>;
  slotsToAdvance?: number;
  onShortlistWinner?: () => void;
  onDismiss?: () => void;
}

const decisionConfig: Record<string, { fg: string; border: string; bg: string; label: string }> = {
  strong:   { fg: '#34d399', border: 'rgba(52,211,153,0.4)', bg: 'rgba(52,211,153,0.1)', label: 'Strong recommendation' },
  moderate: { fg: '#a0aaff', border: 'rgba(91,106,245,0.4)', bg: 'rgba(91,106,245,0.1)', label: 'Recommended'            },
  weak:     { fg: '#fbbf24', border: 'rgba(251,191,36,0.4)', bg: 'rgba(251,191,36,0.1)', label: 'Weak recommendation'    },
};

function initials(name: string | undefined) {
  if (!name) return '?';
  return name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
}

type AdvanceStatus = 'advance' | 'winner' | 'hold';

const ADVANCE_STYLE: Record<AdvanceStatus, { border: string; bg: string; avatarBg: string; chipBg: string; chipFg: string; chipBorder: string; chipLabel: string }> = {
  advance: { border: 'rgba(52,211,153,0.4)', bg: 'rgba(52,211,153,0.06)', avatarBg: '#10b981', chipBg: 'rgba(52,211,153,0.12)', chipFg: '#34d399', chipBorder: 'rgba(52,211,153,0.3)', chipLabel: 'Advance' },
  winner:  { border: 'rgba(52,211,153,0.4)', bg: 'rgba(52,211,153,0.06)', avatarBg: '#10b981', chipBg: 'rgba(52,211,153,0.12)', chipFg: '#34d399', chipBorder: 'rgba(52,211,153,0.3)', chipLabel: 'Winner' },
  hold:    { border: 'var(--color-line)',     bg: 'rgba(255,255,255,0.02)', avatarBg: '#3d4acc', chipBg: 'rgba(107,114,128,0.1)', chipFg: '#9ca3af', chipBorder: 'rgba(107,114,128,0.3)', chipLabel: 'Hold' },
};

function CandidateDimPanel({
  candidate,
  result,
  advanceStatus,
}: {
  candidate: CandidateResponse;
  result: ComparisonResultResponse;
  advanceStatus: AdvanceStatus;
}) {
  const dims = result.dimension_scores;
  const score = result.overall_score ?? 0;
  const s = ADVANCE_STYLE[advanceStatus];

  const dimRows = [
    { label: 'Skills Match',   value: dims?.skills_match    ?? 0 },
    { label: 'Experience Fit', value: dims?.experience_level ?? 0 },
    { label: 'Education',      value: dims?.education        ?? 0 },
    { label: 'Seniority Fit',  value: dims?.seniority_fit    ?? 0 },
  ];

  return (
    <div
      style={{
        flex: 1,
        minWidth: 200,
        border: `1.5px solid ${s.border}`,
        borderRadius: 8,
        padding: '16px 18px',
        background: s.bg,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            background: s.avatarBg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: 13,
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          {initials(candidate.name)}
        </div>
        <div>
          <div style={{ fontWeight: 700, color: '#ededf5', fontSize: 13, lineHeight: 1.2 }}>
            {candidate.name || 'Unknown'}
          </div>
          <div style={{ fontSize: 11, color: (candidate.seniority ? SENIORITY_CONFIG[candidate.seniority]?.fg : undefined) ?? '#64648a' }}>
            {candidate.seniority || candidate.desired_position || '—'}
          </div>
        </div>
        <span
          style={{
            marginLeft: 'auto',
            background: s.chipBg,
            color: s.chipFg,
            border: `1px solid ${s.chipBorder}`,
            borderRadius: 4,
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.04em',
            whiteSpace: 'nowrap',
          }}
        >
          {s.chipLabel}
        </span>
      </div>

      <div
        style={{
          fontFamily: "'Fira Code', ui-monospace, monospace",
          fontSize: 28,
          fontWeight: 800,
          color: '#ededf5',
          lineHeight: 1,
          marginBottom: 4,
        }}
      >
        {score}%
      </div>
      <div style={{ fontSize: 11, color: '#64648a', marginBottom: 14 }}>Overall match score</div>

      {dimRows.map((d) => (
        <div key={d.label} style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ fontSize: 12, color: '#a1a1bb', fontWeight: 500 }}>{d.label}</span>
            <span style={{ fontSize: 12, color: '#a1a1bb', fontFamily: "'Fira Code', monospace" }}>{d.value}%</span>
          </div>
          <div className="dimension-track">
            <div className="dimension-fill" style={{ width: `${d.value}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AIRecommendationCard({
  verdict,
  analysis,
  isLoading,
  isError,
  onRetry,
  results,
  candidatesMap,
  slotsToAdvance = 1,
  onShortlistWinner,
  onDismiss,
}: Props) {
  const isMultiSlot = slotsToAdvance > 1;
  // results are pre-sorted by rank from the backend
  const sortedResults = [...results].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
  const advanceResults = sortedResults.slice(0, slotsToAdvance);
  const holdResults = sortedResults.slice(slotsToAdvance);

  const recommendedResult = verdict
    ? results.find((r) => r.candidate_id === verdict.recommended_candidate_id)
    : null;
  const otherResult = verdict
    ? results.find((r) => r.candidate_id !== verdict.recommended_candidate_id)
    : null;
  const recommendedCandidate = verdict ? candidatesMap.get(verdict.recommended_candidate_id) : null;
  const cfg = verdict ? (decisionConfig[verdict.decision] ?? decisionConfig.moderate) : null;
  const tags = verdict?.decision_tags ?? [];

  const delta =
    !isMultiSlot && recommendedResult && otherResult
      ? (recommendedResult.overall_score ?? 0) - (otherResult.overall_score ?? 0)
      : null;

  return (
    <div id="recommendation" style={{ scrollMarginTop: 20 }}>
      {/* Loading */}
      {isLoading && (
        <div style={{ padding: '8px 0' }}>
          <div className="comparison-loading">
            <div className="comparison-loading-card">
              <div style={{ width: 100, height: 13, borderRadius: 4, background: 'rgba(255,255,255,0.06)', marginBottom: 8 }} />
              <div style={{ width: '72%', height: 10, borderRadius: 4, background: 'rgba(255,255,255,0.06)' }} />
            </div>
            <div className="comparison-loading-card">
              <div style={{ width: 100, height: 13, borderRadius: 4, background: 'rgba(255,255,255,0.06)', marginBottom: 8 }} />
              <div style={{ width: '60%', height: 10, borderRadius: 4, background: 'rgba(255,255,255,0.06)' }} />
            </div>
          </div>
          <div className="parsing-rail" style={{ marginTop: 14, maxWidth: 300 }}>
            <div className="parsing-step is-done">
              <CheckCircleOutlined />
              <span>Comparing skills</span>
            </div>
            <div className="parsing-step is-active">
              <ProfileOutlined />
              <span>Checking seniority</span>
            </div>
            <div className="parsing-step">
              <SafetyCertificateOutlined />
              <span>Preparing recommendation</span>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {isError && !isLoading && (
        <div
          style={{
            background: 'var(--color-panel)',
            border: '1px solid rgba(251,191,36,0.3)',
            borderRadius: 8,
            padding: '24px',
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <ExclamationCircleOutlined style={{ color: '#fbbf24', fontSize: 22 }} />
          <div>
            <p style={{ margin: 0, fontWeight: 600, color: '#ededf5', marginBottom: 4 }}>Analysis failed</p>
            <p style={{ margin: 0, color: '#64648a', fontSize: 13 }}>Could not generate recommendation.</p>
          </div>
          <Button icon={<ReloadOutlined />} onClick={onRetry} style={{ marginLeft: 'auto' }}>
            Retry
          </Button>
        </div>
      )}

      {/* Results */}
      {!isLoading && !isError && verdict && cfg && (
        <div className="recommendation-card">
          {/* Header */}
          <div className="recommendation-summary">
            <div>
              <div
                style={{
                  display: 'inline-block',
                  background: cfg.bg,
                  color: cfg.fg,
                  border: `1px solid ${cfg.border}`,
                  borderRadius: 4,
                  padding: '2px 8px',
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  marginBottom: 8,
                }}
              >
                {isMultiSlot
                  ? `${advanceResults.length} of ${sortedResults.length} to advance`
                  : cfg.label}
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: '#ededf5', letterSpacing: '-0.02em', marginBottom: 8 }}>
                {isMultiSlot
                  ? advanceResults.map((r) => candidatesMap.get(r.candidate_id)?.name).filter(Boolean).join(', ') || 'Top candidates'
                  : recommendedCandidate?.name || 'Candidate'}
              </div>
              <p style={{ margin: 0, fontSize: 13, color: '#a1a1bb', lineHeight: 1.6, maxWidth: 560 }}>
                {verdict.summary}
              </p>
              {tags.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
                  {tags.map((t) => (
                    <span key={t} className="stage-chip stage-shortlisted">{t}</span>
                  ))}
                </div>
              )}
            </div>

            <div className="recommendation-metrics">
              {!isMultiSlot && recommendedResult && (
                <div className="recommendation-metric">
                  <span>Score</span>
                  <strong
                    style={{
                      color: (recommendedResult.overall_score ?? 0) >= 80
                        ? '#34d399'
                        : (recommendedResult.overall_score ?? 0) >= 60
                        ? '#fbbf24'
                        : '#f87171',
                    }}
                  >
                    {recommendedResult.overall_score ?? '—'}
                  </strong>
                </div>
              )}
              {delta !== null && (
                <div className="recommendation-metric">
                  <span>Delta</span>
                  <strong style={{ color: delta >= 0 ? '#34d399' : '#fbbf24' }}>
                    {delta >= 0 ? '+' : ''}{delta}
                  </strong>
                </div>
              )}
              {isMultiSlot && (
                <div className="recommendation-metric">
                  <span>Advancing</span>
                  <strong style={{ color: '#34d399' }}>{advanceResults.length}</strong>
                </div>
              )}
              {isMultiSlot && (
                <div className="recommendation-metric">
                  <span>Holding</span>
                  <strong style={{ color: '#9ca3af' }}>{holdResults.length}</strong>
                </div>
              )}
              <div className="recommendation-metric">
                <span>Confidence</span>
                <strong>
                  {verdict.decision === 'strong' ? 'High' : verdict.decision === 'moderate' ? 'Medium' : 'Low'}
                </strong>
              </div>
            </div>
          </div>

          {/* Candidate dimension panels */}
          <div>
            <div className="dense-label" style={{ marginBottom: 12 }}>Dimension comparison</div>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              {sortedResults.map((r) => {
                const cand = candidatesMap.get(r.candidate_id);
                if (!cand) return null;
                const advanceStatus: AdvanceStatus = isMultiSlot
                  ? ((r.rank ?? 999) <= slotsToAdvance ? 'advance' : 'hold')
                  : (r.candidate_id === verdict.recommended_candidate_id ? 'winner' : 'hold');
                return (
                  <CandidateDimPanel
                    key={r.id}
                    candidate={cand}
                    result={r}
                    advanceStatus={advanceStatus}
                  />
                );
              })}
            </div>
          </div>

          {/* Strengths + Risks — only for single-slot (2-way) */}
          {!isMultiSlot && (
            <div className="recommendation-columns">
              <div className="recommendation-section">
                <div className="dense-label" style={{ marginBottom: 8 }}>
                  <StarOutlined style={{ marginRight: 6 }} />Top strengths
                </div>
                <ul>
                  {([
                    (recommendedResult?.dimension_scores?.skills_match ?? 0) >= 75 && 'Strong technical skill alignment',
                    (recommendedResult?.dimension_scores?.experience_level ?? 0) >= 75 && 'Solid experience foundation',
                    (recommendedResult?.dimension_scores?.seniority_fit ?? 0) >= 75 && 'Well-matched seniority level',
                    (recommendedResult?.dimension_scores?.education ?? 0) >= 75 && 'Relevant educational background',
                    (recommendedResult?.overall_score ?? 0) >= 85 && 'Exceptional overall match',
                  ] as (string | false)[])
                    .filter(Boolean)
                    .slice(0, 3)
                    .map((s, i) => <li key={i}>{s as string}</li>)}
                </ul>
              </div>

              {otherResult && (
                <div className="recommendation-section">
                  <div className="dense-label" style={{ marginBottom: 8 }}>
                    <WarningOutlined style={{ marginRight: 6 }} />Key risks
                  </div>
                  <ul>
                    {([
                      (otherResult.dimension_scores?.skills_match ?? 0) < 60 && 'Skill gaps may require ramp-up',
                      (otherResult.dimension_scores?.experience_level ?? 0) < 60 && 'Experience below role requirements',
                      (otherResult.dimension_scores?.seniority_fit ?? 0) < 60 && 'Seniority mismatch',
                      verdict.decision === 'weak' && 'Neither candidate is an ideal fit',
                    ] as (string | false)[])
                      .filter(Boolean)
                      .slice(0, 3)
                      .map((s, i) => <li key={i}>{s as string}</li>)}
                    {!([
                      (otherResult.dimension_scores?.skills_match ?? 0) < 60,
                      (otherResult.dimension_scores?.experience_level ?? 0) < 60,
                      (otherResult.dimension_scores?.seniority_fit ?? 0) < 60,
                      verdict.decision === 'weak',
                    ].some(Boolean)) && <li>Standard onboarding risks apply</li>}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Skill delta bars — only for exactly 2 candidates */}
          {!isMultiSlot && recommendedResult && otherResult && (
            <div>
              <div className="dense-label" style={{ marginBottom: 12 }}>Skill delta</div>
              <div className="comparison-delta-list">
                {(Object.keys(recommendedResult.dimension_scores) as Array<keyof typeof recommendedResult.dimension_scores>).map((key) => {
                  const winVal = recommendedResult.dimension_scores[key] ?? 0;
                  const loseVal = otherResult.dimension_scores[key] ?? 0;
                  const diff = winVal - loseVal;
                  return (
                    <div key={key} className="comparison-delta-row">
                      <span style={{ textTransform: 'capitalize' }}>{String(key).replace(/_/g, ' ')}</span>
                      <div className="delta-track">
                        <div
                          className="delta-fill"
                          style={{
                            width: `${winVal}%`,
                            background: diff >= 0 ? '#34d399' : '#fbbf24',
                          }}
                        />
                      </div>
                      <span
                        style={{
                          fontFamily: "'Fira Code', monospace",
                          color: diff >= 0 ? '#34d399' : '#f87171',
                        }}
                      >
                        {diff >= 0 ? '+' : ''}{diff}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Full analysis (collapsible) */}
          {analysis && (
            <details style={{ borderTop: '1px solid var(--color-line)', paddingTop: 14 }}>
              <summary
                style={{
                  fontSize: 12,
                  fontWeight: 800,
                  color: '#64648a',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                  userSelect: 'none',
                }}
              >
                Full analysis
              </summary>
              <p
                style={{
                  margin: '12px 0 0',
                  color: '#a1a1bb',
                  fontSize: 13,
                  lineHeight: 1.75,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {analysis}
              </p>
            </details>
          )}

          {/* CTAs */}
          {(onDismiss || onShortlistWinner) && (
            <div className="recommendation-actions">
              {onDismiss && (
                <Button onClick={onDismiss}>Keep reviewing</Button>
              )}
              {onShortlistWinner && (
                <Button type="primary" icon={<StarOutlined />} onClick={onShortlistWinner}>
                  Shortlist winner
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
