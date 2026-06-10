import { BarChartOutlined } from '@ant-design/icons';
import type { ComparisonResultResponse, CandidateResponse } from '../../types';

interface Props {
  left: ComparisonResultResponse;
  right: ComparisonResultResponse;
  candidateLeft: CandidateResponse;
  candidateRight: CandidateResponse;
}

type CellValue =
  | { kind: 'percent'; value: number }
  | { kind: 'raw'; display: string; weight: number };

interface DimRow {
  label: string;
  left: CellValue;
  right: CellValue;
}

function fmt(v: CellValue): string {
  return v.kind === 'percent' ? `${v.value}%` : v.display;
}
function weight(v: CellValue): number {
  return v.kind === 'percent' ? v.value : v.weight;
}

function pct(n: number | null | undefined): CellValue {
  return { kind: 'percent', value: n ?? 0 };
}
function yrs(n: number | null | undefined): CellValue {
  if (n == null) return { kind: 'raw', display: '—', weight: 0 };
  return { kind: 'raw', display: `${n} yrs`, weight: n };
}
function degree(c: CandidateResponse): CellValue {
  const top = c.education?.[0];
  if (!top?.degree) return { kind: 'raw', display: '—', weight: 0 };
  const short = top.degree.split('(')[0].trim();
  return { kind: 'raw', display: short, weight: short.length };
}

const ACCENT_LEFT  = '#38bdf8';
const ACCENT_RIGHT = '#a78bfa';
const LOSE_COLOR   = '#64648a';

export default function CenterColumn({ left, right, candidateLeft, candidateRight }: Props) {
  const leftScore  = left.overall_score  ?? 0;
  const rightScore = right.overall_score ?? 0;

  const gap        = Math.abs(leftScore - rightScore);
  const leftLeads  = leftScore > rightScore;
  const rightLeads = rightScore > leftScore;
  const tied       = leftScore === rightScore;

  const leftFirst  = candidateLeft.name?.split(' ')[0]  ?? 'A';
  const rightFirst = candidateRight.name?.split(' ')[0] ?? 'B';

  const leaderCaption = leftLeads
    ? `${leftFirst} leads by ${gap} pts`
    : rightLeads
    ? `${rightFirst} leads by ${gap} pts`
    : 'Scores are tied';

  const leftDim  = left.dimension_scores;
  const rightDim = right.dimension_scores;

  const rows: DimRow[] = [
    { label: 'Resume Match', left: pct(leftScore), right: pct(rightScore) },
    { label: 'Skills Match', left: pct(leftDim?.skills_match),    right: pct(rightDim?.skills_match)    },
    { label: 'Experience',   left: yrs(candidateLeft.years_experience),  right: yrs(candidateRight.years_experience) },
    { label: 'Education',    left: degree(candidateLeft),         right: degree(candidateRight)         },
    { label: 'Seniority',    left: pct(leftDim?.seniority_fit),   right: pct(rightDim?.seniority_fit)   },
  ];

  const scrollToRecommendation = () => {
    document.getElementById('recommendation')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div
      style={{
        width: 260,
        flexShrink: 0,
        borderRadius: 12,
        border: '1px solid var(--color-line)',
        background: 'var(--color-panel)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        boxShadow: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Score header */}
      <div
        style={{
          width: '100%',
          padding: '20px 16px 16px',
          background: 'linear-gradient(135deg, rgba(91,106,245,0.08) 0%, rgba(255,255,255,0.02) 100%)',
          borderBottom: '1px solid var(--color-line)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          {/* Left score */}
          <div style={{ textAlign: 'center', minWidth: 64 }}>
            <div
              style={{
                fontSize: 34,
                fontWeight: 800,
                lineHeight: 1,
                letterSpacing: '-0.03em',
                fontFamily: 'Fira Code, monospace',
                color: leftLeads || tied ? ACCENT_LEFT : LOSE_COLOR,
                transition: 'color 0.3s',
              }}
            >
              {leftScore}%
            </div>
            <div style={{ fontSize: 10, color: '#a1a1bb', marginTop: 3, fontWeight: 600 }}>{leftFirst}</div>
          </div>

          {/* VS pill */}
          <div
            style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid var(--color-line)',
              borderRadius: 20,
              padding: '6px 12px',
              fontSize: 10,
              fontWeight: 800,
              color: '#64648a',
              letterSpacing: '0.08em',
              flexShrink: 0,
            }}
          >
            VS
          </div>

          {/* Right score */}
          <div style={{ textAlign: 'center', minWidth: 64 }}>
            <div
              style={{
                fontSize: 34,
                fontWeight: 800,
                lineHeight: 1,
                letterSpacing: '-0.03em',
                fontFamily: 'Fira Code, monospace',
                color: rightLeads || tied ? ACCENT_RIGHT : LOSE_COLOR,
                transition: 'color 0.3s',
              }}
            >
              {rightScore}%
            </div>
            <div style={{ fontSize: 10, color: '#a1a1bb', marginTop: 3, fontWeight: 600 }}>{rightFirst}</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', marginTop: 10 }}>
          <span
            style={{
              fontSize: 11,
              color: '#a1a1bb',
              fontWeight: 600,
              padding: '4px 12px',
              background: 'rgba(255,255,255,0.03)',
              borderRadius: 20,
              border: '1px solid var(--color-line)',
              display: 'inline-block',
            }}
          >
            {leaderCaption}
          </span>
        </div>
      </div>

      {/* Dimension rows */}
      <div style={{ width: '100%', padding: '8px 12px' }}>
        {rows.map((row, i) => {
          const lw = weight(row.left);
          const rw = weight(row.right);
          const leftWins  = lw > rw;
          const rightWins = rw > lw;
          return (
            <div
              key={row.label}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto 1fr',
                alignItems: 'center',
                gap: 6,
                padding: '8px 4px',
                borderBottom: i < rows.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
              }}
            >
              <div style={{ textAlign: 'right' }}>
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: leftWins ? 700 : 400,
                    color: leftWins ? ACCENT_LEFT : LOSE_COLOR,
                    transition: 'color 0.2s',
                  }}
                >
                  {fmt(row.left)}
                </span>
              </div>
              <div style={{ textAlign: 'center', minWidth: 90 }}>
                <span
                  style={{
                    fontSize: 10,
                    color: '#64648a',
                    whiteSpace: 'nowrap',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}
                >
                  {row.label}
                </span>
              </div>
              <div style={{ textAlign: 'left' }}>
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: rightWins ? 700 : 400,
                    color: rightWins ? ACCENT_RIGHT : LOSE_COLOR,
                    transition: 'color 0.2s',
                  }}
                >
                  {fmt(row.right)}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ padding: '12px 16px', width: '100%' }}>
        <button
          onClick={scrollToRecommendation}
          style={{
            width: '100%',
            padding: '10px 16px',
            background: 'linear-gradient(135deg, #5b6af5, #6b7aff)',
            border: 'none',
            borderRadius: 10,
            color: '#fff',
            fontSize: 13,
            fontWeight: 700,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            boxShadow: '0 2px 8px rgba(91,106,245,0.3)',
            transition: 'opacity 0.15s, transform 0.15s',
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.9'; (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-1px)'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1';   (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(0)'; }}
        >
          <BarChartOutlined style={{ fontSize: 14 }} />
          View AI Analysis
        </button>
      </div>
    </div>
  );
}
