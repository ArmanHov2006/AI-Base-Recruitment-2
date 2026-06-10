import { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Select, Button, Empty, message, Tag } from 'antd';
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  SwapOutlined,
  TeamOutlined,
} from '@ant-design/icons';

import { getJob } from '../api/jobs';
import { listApplications } from '../api/applications';
import { createComparison, analyzeComparison, listComparisons } from '../api/comparisons';
import type { CandidateResponse, ComparisonResponse, HeadToHeadResponse } from '../types';

import CandidateColumn from '../components/Compare/CandidateColumn';
import CenterColumn from '../components/Compare/CenterColumn';
import AIRecommendationCard from '../components/Compare/AIRecommendationCard';
import ComparisonHistory from '../components/Compare/ComparisonHistory';

function SectionLabel({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ margin: '28px 0 14px' }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: '#64648a', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {title}
      </div>
      {subtitle && (
        <div style={{ fontSize: 12, color: '#a1a1bb', marginTop: 2 }}>{subtitle}</div>
      )}
    </div>
  );
}

export default function CompareCandidates() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [verdict, setVerdict] = useState<HeadToHeadResponse | null>(null);
  const [analyzeError, setAnalyzeError] = useState(false);

  const { data: job, isLoading: jobLoading, isError: jobError } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    retry: false,
  });

  const { data: applications = [], isLoading: appsLoading } = useQuery({
    queryKey: ['applications', jobId],
    queryFn: () => listApplications(jobId!),
    enabled: !!jobId,
  });

  const parsedApps = applications.filter((a) => a.candidate_id != null && a.candidate != null);
  const candidatesMap = new Map<string, CandidateResponse>(
    parsedApps.map((a) => [a.candidate_id as string, a.candidate as CandidateResponse]),
  );
  const candidateOptions = parsedApps.map((a) => ({
    value: a.candidate_id as string,
    label: a.candidate?.name || a.candidate_id,
  }));

  const slotsToAdvance = Math.max(1, parseInt(searchParams.get('slots') ?? '1', 10) || 1);

  // Pre-fill from URL ?candidates=id1,id2,...
  useEffect(() => {
    const param = searchParams.get('candidates');
    if (param && parsedApps.length > 0) {
      const ids = param.split(',').filter((id) => candidatesMap.has(id));
      if (ids.length >= 2) setSelectedIds(ids.slice(0, 20));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, parsedApps.length]);

  const { mutate: runComparison, isPending: isComparing } = useMutation({
    mutationFn: () => createComparison(jobId!, selectedIds),
    onSuccess: (data) => {
      setComparison(data);
      setVerdict(null);
      setAnalyzeError(false);
      triggerAnalyze(data.id);
    },
    onError: () => message.error('Comparison failed. Please try again.'),
  });

  const { mutate: triggerAnalyze, isPending: isAnalyzing } = useMutation({
    mutationFn: (id: string) => analyzeComparison(id),
    onSuccess: (data) => { setVerdict(data); setAnalyzeError(false); },
    onError: () => setAnalyzeError(true),
  });

  const handleRetryAnalyze = useCallback(() => {
    if (comparison) { setAnalyzeError(false); triggerAnalyze(comparison.id); }
  }, [comparison, triggerAnalyze]);

  const handleRerun = useCallback(() => {
    if (selectedIds.length < 2) return;
    setComparison(null); setVerdict(null); setAnalyzeError(false); runComparison();
  }, [selectedIds, runComparison]);

  const handlePickDifferent = useCallback(() => {
    setComparison(null); setVerdict(null); setAnalyzeError(false);
  }, []);

  const handleRestore = useCallback((c: ComparisonResponse) => {
    const ids = c.results.map((r) => r.candidate_id);
    setSelectedIds(ids);
    setComparison(c);
    setVerdict(null);
    setAnalyzeError(false);
  }, []);

  const { data: historyComparisons = [] } = useQuery({
    queryKey: ['comparisons', jobId],
    queryFn: () => listComparisons(jobId!),
    enabled: !!jobId,
    staleTime: 30_000,
  });

  const showHistory = historyComparisons.length > 0;
  const canStart = selectedIds.length >= 2 && new Set(selectedIds).size === selectedIds.length;
  const isBatchMode = selectedIds.length > 2;

  // ── Guards ──────────────────────────────────────────────────────────────────
  if (!jobId || jobError || (!jobLoading && !job)) {
    return (
      <Shell jobId={jobId} jobTitle={undefined} onBack={() => navigate('/jobs')}>
        <div style={{ textAlign: 'center', padding: '64px 0' }}>
          <Empty description="Job not found" />
        </div>
      </Shell>
    );
  }

  if (jobLoading || appsLoading) {
    return (
      <Shell jobId={jobId} jobTitle={job?.title} onBack={() => navigate('/jobs')}>
        <div className="leaderboard-skeleton" style={{ maxWidth: 640, margin: '0 auto' }}>
          {[0, 1, 2].map((i) => (
            <div className="leaderboard-skeleton-row" key={i} />
          ))}
        </div>
      </Shell>
    );
  }

  if (parsedApps.length < 2) {
    return (
      <Shell jobId={jobId} jobTitle={job!.title} onBack={() => navigate(`/jobs/${jobId}`)}>
        <div className="data-panel" style={{ textAlign: 'center', padding: '48px 24px', maxWidth: 480, margin: '0 auto' }}>
          <Empty
            description={
              <div>
                <p style={{ color: '#a1a1bb', marginBottom: 4 }}>
                  Need at least 2 candidates with parsed resumes to compare.
                </p>
                <p style={{ color: '#64648a', fontSize: 13 }}>
                  Currently parsed: {parsedApps.length}
                </p>
              </div>
            }
          >
            <Button type="primary" onClick={() => navigate(`/jobs/${jobId}`)}>
              Back to job
            </Button>
          </Empty>
        </div>
      </Shell>
    );
  }

  // For 2-candidate view: derive left/right
  const [idA, idB] = selectedIds;
  const resultA = comparison?.results.find((r) => r.candidate_id === idA) ?? null;
  const resultB = comparison?.results.find((r) => r.candidate_id === idB) ?? null;
  const candidateA = idA ? (candidatesMap.get(idA) ?? null) : null;
  const candidateB = idB ? (candidatesMap.get(idB) ?? null) : null;

  const recommendedId =
    verdict?.verdict?.recommended_candidate_id ??
    comparison?.verdict?.recommended_candidate_id ??
    null;

  const hasResults = comparison != null && comparison.results.length >= 2;
  const analysis = verdict?.analysis ?? comparison?.head_to_head_analysis ?? null;

  return (
    <Shell jobId={jobId} jobTitle={job!.title} onBack={() => navigate(`/jobs/${jobId}`)}>
      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
        {/* Main content */}
        <div style={{ flex: 1, minWidth: 0 }}>

          {/* Selector panel */}
          {!comparison && (
            <div
              style={{
                background: 'var(--color-panel)',
                border: '1px solid var(--color-line)',
                borderRadius: 8,
                padding: '40px 32px',
                maxWidth: 640,
                margin: '0 auto',
              }}
            >
              <div style={{ marginBottom: 24 }}>
                <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 800, color: '#ededf5', letterSpacing: '-0.02em' }}>
                  Select candidates to compare
                </h2>
                <p style={{ margin: 0, fontSize: 13, color: '#a1a1bb' }}>
                  Choose 2–20 candidates. Profiles are scored against the job requirements and ranked side by side.
                </p>
              </div>

              <div style={{ marginBottom: 16 }}>
                <div className="dense-label" style={{ marginBottom: 6 }}>
                  Candidates
                  {selectedIds.length > 0 && (
                    <span style={{ marginLeft: 8, fontFamily: "'Fira Code', monospace", color: '#5b6af5' }}>
                      {selectedIds.length} selected
                    </span>
                  )}
                </div>
                <Select
                  mode="multiple"
                  style={{ width: '100%' }}
                  placeholder="Search and select candidates…"
                  options={candidateOptions}
                  value={selectedIds}
                  onChange={(v) => setSelectedIds(v.slice(0, 20))}
                  showSearch
                  optionFilterProp="label"
                  size="large"
                  maxTagCount={6}
                  maxTagPlaceholder={(omitted) => `+${omitted} more`}
                />
                {selectedIds.length >= 20 && (
                  <div style={{ fontSize: 12, color: '#fbbf24', marginTop: 4 }}>
                    Maximum 20 candidates reached.
                  </div>
                )}
              </div>

              {selectedIds.length >= 2 && (
                <div style={{ marginBottom: 20, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {selectedIds.map((id) => {
                    const c = candidatesMap.get(id);
                    return (
                      <Tag
                        key={id}
                        closable
                        onClose={() => setSelectedIds((prev) => prev.filter((x) => x !== id))}
                        style={{ fontSize: 12 }}
                      >
                        {c?.name || id.slice(0, 8)}
                      </Tag>
                    );
                  })}
                </div>
              )}

              {isComparing ? (
                <div style={{ padding: '8px 0' }}>
                  <div className="comparison-loading">
                    {selectedIds.slice(0, 3).map((id) => (
                      <div key={id} className="comparison-loading-card" style={{ minHeight: 56 }} />
                    ))}
                  </div>
                  <p style={{ color: '#a1a1bb', fontSize: 13, marginTop: 12, textAlign: 'center' }}>
                    Scoring {selectedIds.length} profiles… typically {selectedIds.length * 15}–{selectedIds.length * 30}s
                  </p>
                </div>
              ) : (
                <div style={{ textAlign: 'center' }}>
                  <Button
                    type="primary"
                    size="large"
                    icon={isBatchMode ? <TeamOutlined /> : undefined}
                    onClick={() => runComparison()}
                    disabled={!canStart}
                    style={{ minWidth: 180 }}
                  >
                    {isBatchMode ? `Compare ${selectedIds.length} Candidates` : 'Start Comparison'}
                  </Button>
                  {isBatchMode && (
                    <p style={{ color: '#64648a', fontSize: 12, marginTop: 10 }}>
                      AI will rank all {selectedIds.length} candidates and identify the best fit
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Results */}
          {hasResults && (
            <>
              {/* Toolbar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 12,
                  padding: '12px 18px',
                  background: 'var(--color-panel)',
                  border: '1px solid var(--color-line)',
                  borderRadius: 8,
                }}
              >
                <div style={{ fontSize: 13, color: '#a1a1bb' }}>
                  Comparing{' '}
                  <span style={{ fontWeight: 700, color: '#ededf5', fontFamily: "'Fira Code', monospace" }}>
                    {comparison!.results.length}
                  </span>
                  {' '}candidates
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button icon={<SwapOutlined />} onClick={handlePickDifferent} disabled={isComparing}>
                    Pick different
                  </Button>
                  <Button icon={<ReloadOutlined />} onClick={handleRerun} disabled={isComparing}>
                    Re-run
                  </Button>
                </div>
              </div>

              {/* Side-by-side columns — only for exactly 2 candidates */}
              {!isBatchMode && candidateA && candidateB && resultA && resultB && (
                <>
                  <SectionLabel
                    title="Side-by-side comparison"
                    subtitle="Per-candidate scoring and dimension breakdown."
                  />
                  <div style={{ display: 'flex', gap: 16, alignItems: 'stretch' }}>
                    <CandidateColumn candidate={candidateA} result={resultA} job={job!} isRecommended={recommendedId === idA} />
                    <CenterColumn left={resultA} right={resultB} candidateLeft={candidateA} candidateRight={candidateB} />
                    <CandidateColumn candidate={candidateB} result={resultB} job={job!} isRecommended={recommendedId === idB} />
                  </div>
                </>
              )}

              <SectionLabel
                title="Recommendation"
                subtitle={
                  isBatchMode
                    ? `Best fit from ${comparison!.results.length} candidates — ranked by score and dimension depth.`
                    : 'Structured verdict from the head-to-head analysis.'
                }
              />
              <AIRecommendationCard
                verdict={verdict?.verdict ?? comparison?.verdict ?? null}
                analysis={analysis}
                isLoading={isAnalyzing}
                isError={analyzeError}
                onRetry={handleRetryAnalyze}
                results={comparison!.results}
                candidatesMap={candidatesMap}
                slotsToAdvance={slotsToAdvance}
                onShortlistWinner={() => {
                  const winId = verdict?.verdict?.recommended_candidate_id ?? comparison?.verdict?.recommended_candidate_id;
                  if (winId) {
                    message.success(`${candidatesMap.get(winId)?.name || 'Candidate'} noted as winner`);
                    navigate(`/candidates/${winId}`);
                  }
                }}
                onDismiss={handlePickDifferent}
              />
            </>
          )}
        </div>

        {/* History sidebar */}
        {showHistory && (
          <ComparisonHistory
            jobId={jobId!}
            candidatesMap={candidatesMap}
            onRestore={handleRestore}
            activeComparisonId={comparison?.id ?? null}
          />
        )}
      </div>
    </Shell>
  );
}

function Shell({
  jobId,
  jobTitle,
  onBack,
  children,
}: {
  jobId: string | undefined;
  jobTitle: string | undefined;
  onBack: () => void;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <div style={{ padding: '0 0 48px', maxWidth: 1600, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, fontSize: 13, color: '#64648a' }}>
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
          role={jobId ? 'link' : undefined}
          tabIndex={jobId ? 0 : undefined}
          style={{ cursor: jobId ? 'pointer' : 'default', color: jobId ? 'var(--color-primary)' : '#64648a', fontWeight: 500 }}
          onClick={() => jobId && navigate(`/jobs/${jobId}`)}
          onKeyDown={(e) => { if (jobId && (e.key === 'Enter' || e.key === ' ')) navigate(`/jobs/${jobId}`); }}
        >
          {jobTitle ?? 'Job'}
        </span>
        <span>/</span>
        <span style={{ color: '#a1a1bb', fontWeight: 600 }} aria-current="page">Compare Candidates</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 24 }}>
        <Button
          shape="circle"
          icon={<ArrowLeftOutlined />}
          onClick={onBack}
          aria-label="Back"
        />
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#ededf5', letterSpacing: '-0.025em' }}>
            Compare Candidates
          </h1>
          {jobTitle && (
            <p style={{ margin: '2px 0 0', fontSize: 13, color: '#a1a1bb', fontWeight: 500 }}>
              {jobTitle}
            </p>
          )}
        </div>
      </div>

      {children}
    </div>
  );
}
