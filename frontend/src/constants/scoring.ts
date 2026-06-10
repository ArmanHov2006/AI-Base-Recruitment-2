export type ScoreTier = 'S' | 'A' | 'B' | 'F' | 'N/A';

export interface TierConfig {
  label: ScoreTier;
  color: string;
  bg: string;
  border: string;
  minScore: number | null;
}

export const SCORE_TIERS: Record<ScoreTier, TierConfig> = {
  'S': {
    label: 'S',
    color: '#10b981', // emerald-500
    bg: 'rgba(16, 185, 129, 0.1)',
    border: 'rgba(16, 185, 129, 0.2)',
    minScore: 8.5,
  },
  'A': {
    label: 'A',
    color: '#3b82f6', // blue-500
    bg: 'rgba(59, 130, 246, 0.1)',
    border: 'rgba(59, 130, 246, 0.2)',
    minScore: 7.0,
  },
  'B': {
    label: 'B',
    color: '#fbbf24', // amber-400
    bg: 'rgba(251, 191, 36, 0.1)',
    border: 'rgba(251, 191, 36, 0.2)',
    minScore: 5.0,
  },
  'F': {
    label: 'F',
    color: '#f87171', // rose-400
    bg: 'rgba(248, 113, 113, 0.1)',
    border: 'rgba(248, 113, 113, 0.2)',
    minScore: 0.0,
  },
  'N/A': {
    label: 'N/A',
    color: '#64648a', // soft
    bg: 'rgba(100, 100, 138, 0.1)',
    border: 'rgba(100, 100, 138, 0.2)',
    minScore: null,
  },
};

export function getTierForScore(score: number | null | undefined): TierConfig {
  if (score == null) return SCORE_TIERS['N/A'];
  
  if (score >= SCORE_TIERS['S'].minScore!) return SCORE_TIERS['S'];
  if (score >= SCORE_TIERS['A'].minScore!) return SCORE_TIERS['A'];
  if (score >= SCORE_TIERS['B'].minScore!) return SCORE_TIERS['B'];
  return SCORE_TIERS['F'];
}
