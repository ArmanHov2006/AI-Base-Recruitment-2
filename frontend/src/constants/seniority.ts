export const SENIORITY_CONFIG: Record<string, { bg: string; fg: string; border: string; label: string }> = {
  junior: { bg: 'rgba(0, 255, 170, 0.15)', fg: '#00ffaa', border: 'rgba(0, 255, 170, 0.4)',  label: 'JUNIOR' },
  mid:    { bg: 'rgba(0, 153, 255, 0.15)',  fg: '#0099ff', border: 'rgba(0, 153, 255, 0.4)',  label: 'MID'    },
  senior: { bg: 'rgba(255, 170, 0, 0.15)',  fg: '#ffaa00', border: 'rgba(255, 170, 0, 0.4)',  label: 'SENIOR' },
  lead:   { bg: 'rgba(204, 0, 255, 0.15)',  fg: '#cc00ff', border: 'rgba(204, 0, 255, 0.4)', label: 'LEAD'   },
};

export const SENIORITY_ANTD_COLORS: Record<string, string> = {
  junior: 'green',
  mid:    'blue',
  senior: 'orange',
  lead:   'purple',
};
