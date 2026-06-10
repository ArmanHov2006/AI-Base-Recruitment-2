import { useQuery } from '@tanstack/react-query';
import { Spin } from 'antd';
import { HistoryOutlined, TrophyOutlined } from '@ant-design/icons';

import { listComparisons } from '../../api/comparisons';
import type { CandidateResponse, ComparisonResponse } from '../../types';

interface Props {
  jobId: string;
  candidatesMap: Map<string, CandidateResponse>;
  onRestore: (comparison: ComparisonResponse) => void;
  activeComparisonId?: string | null;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function getCandidateLabel(candidateId: string, candidatesMap: Map<string, CandidateResponse>): string {
  const c = candidatesMap.get(candidateId);
  if (c?.name) return c.name;
  return candidateId.slice(0, 8) + '…';
}

function getWinner(comparison: ComparisonResponse, candidatesMap: Map<string, CandidateResponse>): string | null {
  if (!comparison.results.length) return null;
  // prefer rank=1, fallback to highest overall_score
  const byRank = comparison.results.find((r) => r.rank === 1);
  if (byRank) return getCandidateLabel(byRank.candidate_id, candidatesMap);
  const byScore = [...comparison.results].sort(
    (a, b) => (b.overall_score ?? 0) - (a.overall_score ?? 0),
  )[0];
  return byScore ? getCandidateLabel(byScore.candidate_id, candidatesMap) : null;
}

function getTopScore(comparison: ComparisonResponse): number | null {
  const scores = comparison.results.map((r) => r.overall_score).filter((s): s is number => s !== null);
  if (!scores.length) return null;
  return Math.max(...scores);
}

export default function ComparisonHistory({ jobId, candidatesMap, onRestore, activeComparisonId }: Props) {
  const { data: comparisons = [], isLoading } = useQuery({
    queryKey: ['comparisons', jobId],
    queryFn: () => listComparisons(jobId),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div style={containerStyle}>
        <SidebarHeader />
        <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 0' }}>
          <Spin size="small" />
        </div>
      </div>
    );
  }

  if (!comparisons.length) {
    return (
      <div style={containerStyle}>
        <SidebarHeader />
        <div
          style={{
            textAlign: 'center',
            padding: '32px 12px',
            color: '#64648a',
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          No prior comparisons yet
        </div>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <SidebarHeader count={comparisons.length} />
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {comparisons.map((comp) => {
          const isActive = comp.id === activeComparisonId;
          const winner = getWinner(comp, candidatesMap);
          const topScore = getTopScore(comp);
          const names = comp.results.map((r) => getCandidateLabel(r.candidate_id, candidatesMap));

          return (
            <button
              key={comp.id}
              onClick={() => onRestore(comp)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                background: isActive ? 'rgba(91,106,245,0.1)' : 'transparent',
                border: 'none',
                borderLeft: isActive ? '3px solid #5b6af5' : '3px solid transparent',
                borderRadius: 0,
                padding: '10px 14px 10px 12px',
                cursor: 'pointer',
                transition: 'background 0.12s',
              }}
              onMouseEnter={(e) => {
                if (!isActive) (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.03)';
              }}
              onMouseLeave={(e) => {
                if (!isActive) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
              }}
            >
              {/* Date row */}
              <div
                style={{
                  fontSize: 11,
                  color: isActive ? '#a0aaff' : '#64648a',
                  fontWeight: 600,
                  marginBottom: 4,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                }}
              >
                {formatDate(comp.created_at)}
              </div>

              {/* Candidate names */}
              <div
                style={{
                  fontSize: 12,
                  color: isActive ? '#ededf5' : '#a1a1bb',
                  fontWeight: 500,
                  marginBottom: 5,
                  lineHeight: 1.4,
                }}
              >
                {names.join(' vs ')}
              </div>

              {/* Winner + score badge row */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                {winner ? (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: 11,
                      color: '#a0aaff',
                      fontWeight: 600,
                      overflow: 'hidden',
                    }}
                  >
                    <TrophyOutlined style={{ fontSize: 10, flexShrink: 0 }} />
                    <span
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {winner}
                    </span>
                  </div>
                ) : (
                  <div />
                )}
                {topScore !== null && (
                  <div
                    style={{
                      background: isActive ? 'rgba(91,106,245,0.18)' : 'rgba(255,255,255,0.06)',
                      color: isActive ? '#a0aaff' : '#a1a1bb',
                      borderRadius: 6,
                      padding: '1px 6px',
                      fontSize: 11,
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {topScore}
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SidebarHeader({ count }: { count?: number }) {
  return (
    <div
      style={{
        padding: '14px 14px 10px',
        borderBottom: '1px solid var(--color-line)',
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        flexShrink: 0,
      }}
    >
      <HistoryOutlined style={{ fontSize: 13, color: '#64648a' }} />
      <span style={{ fontSize: 12, fontWeight: 700, color: '#a1a1bb', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        History
      </span>
      {count !== undefined && count > 0 && (
        <span
          style={{
            marginLeft: 'auto',
            background: 'rgba(255,255,255,0.06)',
            color: '#a1a1bb',
            borderRadius: 10,
            padding: '1px 7px',
            fontSize: 11,
            fontWeight: 700,
          }}
        >
          {count}
        </span>
      )}
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  width: 280,
  flexShrink: 0,
  background: 'var(--color-panel)',
  border: '1px solid var(--color-line)',
  borderRadius: 12,
  display: 'flex',
  flexDirection: 'column',
  alignSelf: 'flex-start',
  maxHeight: 'calc(100vh - 180px)',
  position: 'sticky',
  top: 24,
  overflow: 'hidden',
  boxShadow: 'none',
};
