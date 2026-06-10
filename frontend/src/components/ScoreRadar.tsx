/**
 * Data-driven radar chart for a candidate's dimension scores. Pure SVG, no
 * library, no fabricated data — it only renders the real 0-100 dimension
 * numbers the scorer produced. This is a chart, not decoration.
 */

const AXES = [
  { key: 'skills_match', label: 'Skills' },
  { key: 'experience_level', label: 'Experience' },
  { key: 'education', label: 'Education' },
  { key: 'seniority_fit', label: 'Seniority' },
] as const;

interface ScoreRadarProps {
  scores: Record<string, number>;
  size?: number;
}

const PRIMARY = '#5b6af5';
const GRID = 'rgba(255,255,255,0.1)';
const LABEL = '#a1a1bb';

export default function ScoreRadar({ scores, size = 168 }: ScoreRadarProps) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 28; // leave room for labels
  const n = AXES.length;

  // angle for axis i, starting at top (-90deg), clockwise
  const angle = (i: number) => (-90 + (360 / n) * i) * (Math.PI / 180);
  const point = (i: number, radius: number) => ({
    x: cx + radius * Math.cos(angle(i)),
    y: cy + radius * Math.sin(angle(i)),
  });

  const valuePoints = AXES.map((axis, i) => {
    const v = Math.max(0, Math.min(100, scores[axis.key] ?? 0));
    return point(i, (v / 100) * r);
  });
  const polygon = valuePoints.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');

  const rings = [0.25, 0.5, 0.75, 1];
  const summary = AXES.map((a) => `${a.label} ${scores[a.key] ?? 0}`).join(', ');

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      overflow="visible"
      role="img"
      aria-label={`Dimension scores: ${summary}`}
    >
      {/* grid rings */}
      {rings.map((ring) => (
        <polygon
          key={ring}
          points={AXES.map((_, i) => {
            const p = point(i, r * ring);
            return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
          }).join(' ')}
          fill="none"
          stroke={GRID}
          strokeWidth={1}
        />
      ))}

      {/* axis spokes */}
      {AXES.map((_, i) => {
        const p = point(i, r);
        return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke={GRID} strokeWidth={1} />;
      })}

      {/* value shape */}
      <polygon points={polygon} fill={PRIMARY} fillOpacity={0.16} stroke={PRIMARY} strokeWidth={2} />
      {valuePoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill={PRIMARY} />
      ))}

      {/* labels */}
      {AXES.map((axis, i) => {
        const p = point(i, r + 16);
        const anchor = Math.abs(p.x - cx) < 2 ? 'middle' : p.x > cx ? 'start' : 'end';
        return (
          <text
            key={axis.key}
            x={p.x}
            y={p.y}
            dy={4}
            textAnchor={anchor}
            fontSize={11}
            fontWeight={700}
            fill={LABEL}
          >
            {axis.label}
          </text>
        );
      })}
    </svg>
  );
}
