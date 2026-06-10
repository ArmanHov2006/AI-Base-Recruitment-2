import { Typography, Divider, Tooltip } from 'antd';
import { Link } from 'react-router-dom';
import { EnvironmentOutlined, BankOutlined, CalendarOutlined, ArrowRightOutlined } from '@ant-design/icons';
import type { ComparisonResultResponse, JobResponse, CandidateResponse } from '../../types';
import { SENIORITY_CONFIG } from '../../constants/seniority';

const { Text, Title } = Typography;

interface Props {
  candidate: CandidateResponse;
  result: ComparisonResultResponse;
  job: JobResponse;
  isRecommended: boolean;
}

const AVATAR_COLORS = ['#5b6af5', '#7c3aed', '#db2777', '#d97706', '#10b981', '#f87171', '#0891b2'];
function avatarColor(name: string | undefined) {
  if (!name) return '#64648a';
  return AVATAR_COLORS[name.charCodeAt(0) % AVATAR_COLORS.length];
}
function initials(name: string | undefined) {
  if (!name) return '?';
  return name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
}

// Dark-theme match tiers — tinted backgrounds over the dark panel surface.
function matchTier(score: number) {
  if (score >= 85) return { label: 'High Match',    bg: 'rgba(52,211,153,0.1)',  fg: '#34d399', bar: '#34d399', caption: 'Strong match'  };
  if (score >= 70) return { label: 'Good Match',    bg: 'rgba(91,106,245,0.1)',  fg: '#a0aaff', bar: '#5b6af5', caption: 'Good match'    };
  return             { label: 'Partial Match', bg: 'rgba(251,191,36,0.1)',  fg: '#fbbf24', bar: '#fbbf24', caption: 'Partial match' };
}

function SkillBar({ name, score, barColor }: { name: string; score: number; barColor: string }) {
  const missing = score === 0;
  return (
    <div style={{ marginBottom: 9 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 12, color: missing ? '#64648a' : '#ededf5', fontWeight: 500 }}>{name}</span>
        <span style={{ fontSize: 12, color: missing ? '#64648a' : '#a1a1bb', fontWeight: 600 }}>{score}%</span>
      </div>
      <div style={{ height: 5, borderRadius: 99, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            width: `${score}%`,
            borderRadius: 99,
            background: missing ? 'rgba(255,255,255,0.12)' : `linear-gradient(90deg, ${barColor}80, ${barColor})`,
            transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
          }}
        />
      </div>
    </div>
  );
}

export default function CandidateColumn({ candidate, result, job, isRecommended }: Props) {
  const overallScore = result.overall_score ?? 0;
  const tier = matchTier(overallScore);
  const accent = avatarColor(candidate.name);
  const techSkills = job.required_technical_skills ?? [];
  const softSkills = job.required_soft_skills ?? [];

  const techScoreMap = new Map<string, number>(
    (result.skill_breakdown?.technical ?? []).map((s) => [s.name.toLowerCase(), s.score]),
  );
  const softScoreMap = new Map<string, number>(
    (result.skill_breakdown?.soft ?? []).map((s) => [s.name.toLowerCase(), s.score]),
  );

  const topEducation = candidate.education?.[0];
  const roleLine = candidate.desired_position || candidate.seniority;
  const roleColor = !candidate.desired_position && candidate.seniority
    ? SENIORITY_CONFIG[candidate.seniority]?.fg
    : undefined;

  return (
    <div
      className={isRecommended ? 'compare-col-recommended' : undefined}
      style={{
        flex: 1,
        minWidth: 240,
        borderRadius: 12,
        border: isRecommended ? `1.5px solid ${accent}55` : '1px solid var(--color-line)',
        background: isRecommended
          ? `linear-gradient(160deg, ${accent}14 0%, var(--color-panel) 55%)`
          : 'var(--color-panel)',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: isRecommended ? `0 4px 24px ${accent}22, 0 0 0 1px ${accent}30` : 'none',
        overflow: 'hidden',
      }}
    >
      {/* AI PICK ribbon */}
      {isRecommended && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            right: 20,
            background: accent,
            color: '#fff',
            fontSize: 9,
            fontWeight: 800,
            padding: '5px 12px',
            borderRadius: '0 0 10px 10px',
            letterSpacing: '0.1em',
            boxShadow: `0 2px 8px ${accent}40`,
          }}
        >
          AI PICK
        </div>
      )}

      <div style={{ padding: '24px 22px', display: 'flex', flexDirection: 'column', flex: 1 }}>
        {/* Avatar + identity */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 18, paddingRight: isRecommended ? 56 : 0 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: '50%',
              background: accent,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: 18,
              fontWeight: 700,
              flexShrink: 0,
              border: `2px solid ${accent}40`,
              boxShadow: `0 0 0 4px ${accent}1f`,
            }}
          >
            {initials(candidate.name)}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
              <Title level={5} style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#ededf5', lineHeight: 1.3 }}>
                {candidate.name || 'Unknown'}
              </Title>
              <span
                style={{
                  background: tier.bg,
                  color: tier.fg,
                  border: `1px solid ${tier.fg}40`,
                  borderRadius: 20,
                  padding: '2px 10px',
                  fontSize: 11,
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                }}
              >
                {tier.label}
              </span>
            </div>
            {roleLine && (
              <Text style={{ fontSize: 12, color: roleColor ?? '#a1a1bb', fontWeight: 500, display: 'block', marginTop: 2 }}>
                {roleLine}
              </Text>
            )}
            {candidate.location && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 3 }}>
                <EnvironmentOutlined style={{ color: '#64648a', fontSize: 11 }} />
                <Text style={{ fontSize: 11, color: '#64648a' }}>{candidate.location}</Text>
              </div>
            )}
          </div>
        </div>

        {/* Score display */}
        <div
          style={{
            background: `${accent}14`,
            border: `1px solid ${accent}30`,
            borderRadius: 12,
            padding: '14px 16px',
            marginBottom: 16,
          }}
        >
          <div style={{ fontSize: 11, color: '#64648a', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
            Resume Match
          </div>
          <div style={{ fontSize: 40, fontWeight: 800, color: accent, letterSpacing: '-0.035em', lineHeight: 1, marginBottom: 6, fontFamily: 'Fira Code, monospace' }}>
            {overallScore}%
          </div>
          <div style={{ height: 6, borderRadius: 99, background: `${accent}25`, overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${overallScore}%`,
                background: `linear-gradient(90deg, ${accent}70, ${accent})`,
                borderRadius: 99,
                transition: 'width 0.8s cubic-bezier(0.4,0,0.2,1)',
              }}
            />
          </div>
          <Text style={{ fontSize: 11, color: '#64648a', marginTop: 4, display: 'block' }}>{tier.caption}</Text>
        </div>

        {/* Dimension mini-bars */}
        {result.dimension_scores && (
          <>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64648a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Dimensions
            </div>
            {[
              { label: 'Skills',     value: result.dimension_scores.skills_match    ?? 0 },
              { label: 'Experience', value: result.dimension_scores.experience_level ?? 0 },
              { label: 'Education',  value: result.dimension_scores.education        ?? 0 },
              { label: 'Seniority',  value: result.dimension_scores.seniority_fit    ?? 0 },
            ].map((d) => (
              <div key={d.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
                <span style={{ width: 68, fontSize: 11, color: '#a1a1bb', flexShrink: 0 }}>{d.label}</span>
                <div style={{ flex: 1, height: 5, borderRadius: 99, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${d.value}%`, background: `linear-gradient(90deg, ${accent}60, ${accent})`, borderRadius: 99 }} />
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: accent, minWidth: 28, textAlign: 'right' }}>{d.value}%</span>
              </div>
            ))}
            <Divider style={{ margin: '12px 0', borderColor: 'var(--color-line)' }} />
          </>
        )}

        {/* Technical Skills */}
        {techSkills.length > 0 && (
          <>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64648a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Technical Skills
            </div>
            {techSkills.map((skill) => (
              <SkillBar key={skill} name={skill} score={techScoreMap.get(skill.toLowerCase()) ?? 0} barColor={accent} />
            ))}
            <Divider style={{ margin: '12px 0', borderColor: 'var(--color-line)' }} />
          </>
        )}

        {/* Soft Skills */}
        {softSkills.length > 0 && (
          <>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64648a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Soft Skills
            </div>
            {softSkills.map((skill) => (
              <SkillBar key={skill} name={skill} score={softScoreMap.get(skill.toLowerCase()) ?? 0} barColor={accent} />
            ))}
            <Divider style={{ margin: '12px 0', borderColor: 'var(--color-line)' }} />
          </>
        )}

        {/* Reasoning */}
        {result.reasoning && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64648a', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              Scoring Rationale
            </div>
            <p style={{ color: '#a1a1bb', fontSize: 12, marginBottom: 0, lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>
              {result.reasoning}
            </p>
          </div>
        )}

        {/* Bottom tiles */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          {candidate.years_experience != null && (
            <Tooltip title="Years of experience">
              <div style={tileStyle}>
                <CalendarOutlined style={{ color: accent, marginBottom: 2, fontSize: 14 }} />
                <div style={{ fontWeight: 700, fontSize: 14, color: '#ededf5' }}>{candidate.years_experience}</div>
                <div style={{ fontSize: 10, color: '#64648a' }}>yrs exp</div>
              </div>
            </Tooltip>
          )}
          {topEducation && (
            <Tooltip title={topEducation.institution}>
              <div style={tileStyle}>
                <BankOutlined style={{ color: accent, marginBottom: 2, fontSize: 14 }} />
                <div style={{ fontWeight: 600, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#ededf5', maxWidth: 80 }}>
                  {topEducation.degree || 'Degree'}
                </div>
                <div style={{ fontSize: 10, color: '#64648a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 80 }}>
                  {topEducation.institution}
                </div>
              </div>
            </Tooltip>
          )}
        </div>

        {/* View profile link */}
        <Link
          to={`/candidates/${candidate.id}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '9px',
            background: `${accent}14`,
            border: `1px solid ${accent}30`,
            borderRadius: 10,
            color: accent,
            fontSize: 12,
            fontWeight: 600,
            textDecoration: 'none',
            transition: 'background 0.15s',
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.background = `${accent}24`)}
          onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.background = `${accent}14`)}
        >
          View Full Profile <ArrowRightOutlined style={{ fontSize: 10 }} />
        </Link>
      </div>
    </div>
  );
}

const tileStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 72,
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid var(--color-line)',
  borderRadius: 10,
  padding: '10px 12px',
  textAlign: 'center',
};
