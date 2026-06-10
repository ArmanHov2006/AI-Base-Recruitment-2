import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button, Empty } from 'antd';
import { RightOutlined, DownOutlined, UserOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

import { getJobLeaderboard } from '../api/jobs';
import type { LeaderboardEntry } from '../types';

interface Props {
  jobId: string;
}

function scoreClass(score: number | null): string {
  if (score === null) return 'score-neutral';
  if (score >= 80) return 'score-high';
  if (score >= 60) return 'score-medium';
  return 'score-low';
}

function rankClass(rank: number): string {
  if (rank <= 3) return `rank-${rank}`;
  return '';
}

function LeaderboardSkeleton() {
  return (
    <div className="leaderboard-skeleton">
      {[0, 1, 2, 3].map((i) => (
        <div className="leaderboard-skeleton-row" key={i} />
      ))}
    </div>
  );
}

function EntryRow({ entry }: { entry: LeaderboardEntry }) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const dims = entry.dimension_scores;
  const dimKeys = Object.keys(dims);
  const topDims = dimKeys.slice(0, 2);
  const isFirst = entry.rank === 1;
  const rc = rankClass(entry.rank);

  return (
    <div className="leaderboard-row-wrap">
      <div className={`leaderboard-row${isFirst ? ' is-first' : ''}`}>
        {/* Rank */}
        <div>
          <span className={`rank-badge${rc ? ` ${rc}` : ''}`}>#{entry.rank}</span>
        </div>

        {/* Candidate */}
        <div>
          <div style={{ fontWeight: 700, color: '#ededf5', fontSize: 14 }}>
            {entry.candidate_name || 'Unknown'}
          </div>
          {entry.candidate_seniority && (
            <div style={{ fontSize: 12, color: '#a1a1bb', marginTop: 2 }}>
              {entry.candidate_seniority}
            </div>
          )}
        </div>

        {/* Score */}
        <div>
          <span className={`score-badge ${scoreClass(entry.overall_score)}`}>
            {entry.overall_score != null ? `${entry.overall_score}` : '—'}
          </span>
        </div>

        {/* Email */}
        <div style={{ fontSize: 12, color: '#a1a1bb', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {entry.candidate_email || '—'}
        </div>

        {/* Dimension preview */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {topDims.map((key) => {
            const val = dims[key] ?? 0;
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, color: '#a1a1bb', width: 80, flexShrink: 0, textTransform: 'capitalize', whiteSpace: 'nowrap' }}>
                  {key.replace(/_/g, ' ')}
                </span>
                <div className="dimension-track" style={{ flex: 1 }}>
                  <div className="dimension-fill" style={{ width: `${val}%` }} />
                </div>
                <span style={{ fontFamily: "'Fira Code', monospace", fontSize: 11, color: '#a1a1bb', width: 28, textAlign: 'right', flexShrink: 0 }}>
                  {val}
                </span>
              </div>
            );
          })}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', alignItems: 'center' }}>
          <Button
            size="small"
            icon={<UserOutlined />}
            onClick={() => navigate(`/candidates/${entry.candidate_id}`)}
            aria-label="View candidate profile"
          />
          <Button
            type="text"
            size="small"
            icon={expanded ? <DownOutlined /> : <RightOutlined />}
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? 'Collapse details' : 'Expand details'}
          />
        </div>
      </div>

      {expanded && (
        <div className="leaderboard-details">
          {/* All dimensions */}
          <div>
            <div className="dense-label" style={{ marginBottom: 10 }}>All dimensions</div>
            <div className="dimension-list">
              {dimKeys.map((key) => {
                const val = dims[key] ?? 0;
                return (
                  <div key={key} className="dimension-row">
                    <span style={{ textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</span>
                    <div className="dimension-track">
                      <div className="dimension-fill" style={{ width: `${val}%` }} />
                    </div>
                    <span style={{ fontFamily: "'Fira Code', monospace", fontSize: 12 }}>{val}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Technical skills */}
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

          {/* Reasoning + link */}
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
              View full profile →
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function JobLeaderboard({ jobId }: Props) {
  const navigate = useNavigate();
  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['leaderboard', jobId],
    queryFn: () => getJobLeaderboard(jobId),
    staleTime: 30_000,
  });

  if (isLoading) {
    return <LeaderboardSkeleton />;
  }

  if (!entries.length) {
    return (
      <div className="data-panel" style={{ textAlign: 'center', padding: '48px 24px' }}>
        <Empty
          description={
            <span style={{ color: '#a1a1bb' }}>
              No candidates scored yet. Run a comparison to populate the leaderboard.
            </span>
          }
        >
          <Button type="primary" onClick={() => navigate(`/jobs/${jobId}/compare`)}>
            Compare candidates
          </Button>
        </Empty>
      </div>
    );
  }

  return (
    <div className="leaderboard-panel">
      <div className="leaderboard-head">
        <div>#</div>
        <div>Candidate</div>
        <div>Score</div>
        <div>Contact</div>
        <div>Dimensions</div>
        <div />
      </div>
      {entries.map((entry) => (
        <EntryRow key={entry.candidate_id} entry={entry} />
      ))}
    </div>
  );
}
