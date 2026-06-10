import { SENIORITY_CONFIG } from '../../constants/seniority';

interface SeniorityBadgeProps {
  seniority: string | null | undefined;
  size?: 'sm' | 'md';
}

export default function SeniorityBadge({ seniority, size = 'md' }: SeniorityBadgeProps) {
  if (!seniority) return null;
  const cfg = SENIORITY_CONFIG[seniority];
  if (!cfg) return null;

  const padding = size === 'sm' ? '2px 8px' : '4px 12px';
  const fontSize = size === 'sm' ? 11 : 12;

  return (
    <span
      style={{
        display: 'inline-block',
        padding,
        background: cfg.bg,
        color: cfg.fg,
        border: 'none',
        borderRadius: 4,
        fontSize,
        fontWeight: 700,
        lineHeight: 1.4,
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
      }}
    >
      {cfg.label}
    </span>
  );
}
