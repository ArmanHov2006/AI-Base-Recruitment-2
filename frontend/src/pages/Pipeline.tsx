import { memo, useCallback, useMemo, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, DatePicker, Dropdown, Empty, Input, Modal, Select, message } from 'antd';
import {
  ArrowLeftOutlined,
  CalendarOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  LoadingOutlined,
  MoreOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import dayjs from 'dayjs';

import { getJob, listJobs } from '../api/jobs';
import { listApplications, setInterview, updateApplicationStatus } from '../api/applications';
import type { JobApplication, UserSettableStatus } from '../types';
import { SENIORITY_CONFIG } from '../constants/seniority';
import { getTierForScore } from '../constants/scoring';
import { useAuth } from '../context/AuthContext';

const ACTIVE_COLUMNS: { status: UserSettableStatus; label: string }[] = [
  { status: 'applied',     label: 'Applied' },
  { status: 'reviewing',   label: 'Reviewing' },
  { status: 'shortlisted', label: 'Shortlisted' },
  { status: 'interview',   label: 'Interview' },
  { status: 'offer',       label: 'Offer' },
];

const TERMINAL_COLUMNS: { status: UserSettableStatus; label: string }[] = [
  { status: 'hired', label: 'Hired' },
  { status: 'rejected', label: 'Rejected' },
  { status: 'withdrawn', label: 'Withdrawn' },
];

const COLUMNS = [...ACTIVE_COLUMNS, ...TERMINAL_COLUMNS];

// Forward order for skip detection (terminal stages excluded — always allowed)
const STAGE_PROGRESSION: UserSettableStatus[] = ['applied', 'reviewing', 'shortlisted', 'interview', 'offer', 'hired'];

function isStageSkip(from: UserSettableStatus, to: UserSettableStatus): boolean {
  const fi = STAGE_PROGRESSION.indexOf(from);
  const ti = STAGE_PROGRESSION.indexOf(to);
  return fi !== -1 && ti !== -1 && Math.abs(ti - fi) > 1;
}

type ApplicationsByStatus = Record<UserSettableStatus, JobApplication[]>;

const EMPTY_GROUPS = COLUMNS.reduce((acc, column) => {
  acc[column.status] = [];
  return acc;
}, {} as ApplicationsByStatus);

const AVATAR_PALETTE = [
  '#3d4acc', '#10b981', '#7c3aed', '#d97706', '#e11d48',
  '#0891b2', '#c2410c', '#15803d',
];
function avatarBg(seed: string): string {
  const sum = seed.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return AVATAR_PALETTE[sum % AVATAR_PALETTE.length];
}
function cardInitials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  return parts.slice(0, 2).map((p) => p[0]?.toUpperCase()).join('');
}

function shortApplicationRef(applicationId: string): string {
  return `#${applicationId.split('-').join('').slice(-6).toUpperCase()}`;
}

function displayName(app: JobApplication): string {
  const name = app.candidate?.name?.trim();
  if (name) return name;
  const email = app.candidate?.email?.trim();
  if (email) return email;
  return shortApplicationRef(app.id);
}


const PipelineScoreBadge = memo(function PipelineScoreBadge({ app }: { app: JobApplication }) {
  const score = app.overall_score_10;
  const tier = getTierForScore(score);

  return (
    <span
      className={`kanban-score-badge ${score == null ? 'is-empty' : ''}`}
      style={{
        color: tier.color,
        background: tier.bg,
        borderColor: tier.border,
      }}
    >
      <span className="kanban-score-ai" style={{ color: tier.color, opacity: 0.8 }}>AI</span>
      {score != null ? `${score.toFixed(1)}/10` : 'N/A'}
    </span>
  );
});

const PipelineCard = memo(function PipelineCard({
  app,
  isDragging,
  isReadOnly,
  onDragStart,
  onDragEnd,
  onMove,
  onOpenCandidate,
  onScheduleInterview,
}: {
  app: JobApplication;
  isDragging: boolean;
  isReadOnly: boolean;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onMove: (app: JobApplication, status: UserSettableStatus) => void;
  onOpenCandidate: (candidateId: string) => void;
  onScheduleInterview: (app: JobApplication) => void;
}) {
  const candidateName = app.candidate?.name?.trim();
  const candidateEmail = app.candidate?.email?.trim();
  const needsReview = !candidateName;
  const appRef = shortApplicationRef(app.id);
  const title = displayName(app);
  const seniority = app.candidate?.seniority?.toLowerCase() || '';
  const seniorityKey = seniority === 'medium' ? 'mid' : seniority;
  const seniorityConfig = SENIORITY_CONFIG[seniorityKey];

  const daysInStage = Math.floor(
    (Date.now() - new Date(app.updated_at).getTime()) / 86400000,
  );

  const showInterviewDate = app.status === 'interview' && app.interview_scheduled_at;

  const moveMenu: MenuProps = {
    items: COLUMNS.filter((c) => c.status !== app.status).map((c) => ({
      key: c.status,
      label: `Move to ${c.label}`,
    })),
    onClick: ({ key }) => onMove(app, key as UserSettableStatus),
  };

  return (
    <article
      className={`kanban-card${isDragging ? ' is-dragging' : ''}`}
      draggable={!isReadOnly}
      onDragStart={isReadOnly ? undefined : (event) => {
        onDragStart(app.id);
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', app.id);
      }}
      onDragEnd={isReadOnly ? undefined : onDragEnd}
    >
      <div
        className="kanban-card-inner"
        style={{
          borderLeftColor: seniorityConfig?.fg || 'transparent',
          background: seniorityConfig
            ? `linear-gradient(90deg, ${seniorityConfig.bg} 0%, transparent 100%)`
            : undefined,
        }}
      >
        {app.candidate_id && (
          <div
            className="kanban-card-link-overlay"
            role="button"
            tabIndex={0}
            onClick={() => onOpenCandidate(app.candidate_id!)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onOpenCandidate(app.candidate_id!);
              }
            }}
            aria-label={`View ${title} profile`}
          />
        )}

        <div className="kanban-card-top">
          <span className="kanban-avatar" style={{ background: avatarBg(app.candidate_id || app.id) }}>
            {cardInitials(title)}
          </span>
          <div className="kanban-card-id">
            <strong>{title}</strong>
            {needsReview && <span className="kanban-review-flag">Needs review</span>}
          </div>
          {!isReadOnly && (
            <div className="kanban-card-dropdown-btn">
              <Dropdown menu={moveMenu} trigger={['click']} placement="bottomRight">
                <Button
                  type="text"
                  size="small"
                  icon={<MoreOutlined style={{ fontSize: 13 }} />}
                  onClick={(event) => event.stopPropagation()}
                  style={{ width: 24, height: 24, padding: 0, border: 'none', background: 'transparent' }}
                  aria-label="Move application"
                />
              </Dropdown>
            </div>
          )}
        </div>

        <div className="kanban-card-meta">
          {seniorityConfig && (
            <span
              className="kanban-card-seniority"
              style={{ color: seniorityConfig.fg, background: seniorityConfig.bg, borderColor: seniorityConfig.border }}
            >
              {seniorityConfig.label}
            </span>
          )}
          <span className="kanban-card-email" title={candidateEmail || appRef}>
            {candidateEmail || appRef}
          </span>
          {showInterviewDate ? (
            <span style={{ fontSize: 11, color: 'var(--color-primary, #5b6af5)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 130 }}>
              {new Date(app.interview_scheduled_at!).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
          ) : (
            <PipelineScoreBadge app={app} />
          )}
          {daysInStage > 0 && (
            <span style={{ fontSize: 10, color: 'var(--color-muted)', marginLeft: 'auto', flexShrink: 0 }}>
              {daysInStage}d
            </span>
          )}
        </div>

        <div className="kanban-card-interview" style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
          {!isReadOnly && (
            <Button
              type="text"
              size="small"
              icon={<CalendarOutlined style={{ fontSize: 12, color: app.interview_scheduled_at ? 'var(--color-primary, #5b6af5)' : 'var(--color-muted)' }} />}
              onClick={(event) => { event.stopPropagation(); onScheduleInterview(app); }}
              style={{ padding: '0 4px', height: 20, border: 'none', background: 'transparent' }}
              aria-label="Schedule interview"
            />
          )}
          {app.interview_scheduled_at && app.status !== 'interview' && (
            <span style={{ fontSize: 11, color: 'var(--color-primary, #5b6af5)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 130 }}>
              {new Date(app.interview_scheduled_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>
    </article>
  );
});

export default function Pipeline() {
  const { jobId: jobIdParam } = useParams<{ jobId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const jobId = jobIdParam ?? searchParams.get('jobId') ?? undefined;
  const isTopLevel = !jobIdParam;
  const isReadOnly = user?.role === 'viewer';

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<UserSettableStatus | null>(null);
  const [showTerminal, setShowTerminal] = useState(false);
  const [interviewApp, setInterviewApp] = useState<JobApplication | null>(null);
  const [interviewAt, setInterviewAt] = useState<dayjs.Dayjs | null>(null);
  const [interviewLocation, setInterviewLocation] = useState<string>('');

  const visibleColumns = showTerminal ? COLUMNS : ACTIVE_COLUMNS;

  const { data: jobs = [] } = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    enabled: isTopLevel,
  });

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    retry: false,
  });

  const { data: applications = [], isLoading: appsLoading } = useQuery({
    queryKey: ['applications', jobId],
    queryFn: () => listApplications(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      if (draggingId) return false;
      return query.state.data?.some((a) => a.status === 'parsing') ? 2000 : false;
    },
  });

  const groupedApplications = useMemo(() => {
    const groups: ApplicationsByStatus = COLUMNS.reduce((acc, column) => {
      acc[column.status] = [];
      return acc;
    }, {} as ApplicationsByStatus);

    for (const app of applications) {
      if (app.status in groups) {
        groups[app.status as UserSettableStatus].push(app);
      }
    }
    return groups;
  }, [applications]);

  const parsingSummary = useMemo(() => {
    let parsing = 0;
    let failed = 0;
    for (const app of applications) {
      if (app.status === 'parsing') parsing += 1;
      if (app.status === 'parse_failed') failed += 1;
    }
    return { parsing, failed, total: parsing + failed };
  }, [applications]);

  const moveMutation = useMutation({
    mutationFn: ({ appId, status }: { appId: string; status: UserSettableStatus }) =>
      updateApplicationStatus(jobId!, appId, status),
    onMutate: async ({ appId, status }) => {
      await queryClient.cancelQueries({ queryKey: ['applications', jobId] });
      const prev = queryClient.getQueryData<JobApplication[]>(['applications', jobId]);
      queryClient.setQueryData<JobApplication[]>(['applications', jobId], (old) =>
        (old ?? []).map((a) => (a.id === appId ? { ...a, status } : a)),
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['applications', jobId], ctx.prev);
      message.error('Could not move candidate');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['applications', jobId] });
    },
  });

  const openInterviewModal = useCallback((app: JobApplication) => {
    setInterviewApp(app);
    setInterviewAt(app.interview_scheduled_at ? dayjs(app.interview_scheduled_at) : null);
    setInterviewLocation(app.interview_location ?? '');
  }, []);

  const move = useCallback((app: JobApplication, newStatus: UserSettableStatus) => {
    if (app.status === newStatus) return;

    const doMove = () => {
      moveMutation.mutate({ appId: app.id, status: newStatus });
      if (newStatus === 'interview') openInterviewModal(app);
    };

    if (isStageSkip(app.status as UserSettableStatus, newStatus)) {
      Modal.confirm({
        title: 'Skip stages?',
        content: `Moving from "${app.status}" to "${newStatus}" skips intermediate stages. Confirm?`,
        okText: 'Move anyway',
        cancelText: 'Cancel',
        onOk: doMove,
      });
      return;
    }
    doMove();
  }, [moveMutation, openInterviewModal]);

  const handleDrop = useCallback((status: UserSettableStatus) => {
    setDragOver(null);
    const app = applications.find((a) => a.id === draggingId);
    setDraggingId(null);
    if (app) move(app, status);
  }, [applications, draggingId, move]);

  const handleDragStart = useCallback((id: string) => {
    setDraggingId(id);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggingId(null);
    setDragOver(null);
  }, []);

  const openCandidate = useCallback((candidateId: string) => {
    navigate(`/candidates/${candidateId}`);
  }, [navigate]);

  const interviewMutation = useMutation({
    mutationFn: ({ appId, scheduledAt, location }: { appId: string; scheduledAt: string | null; location: string | null }) =>
      setInterview(jobId!, appId, scheduledAt, location),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications', jobId] });
      message.success('Interview updated');
      setInterviewApp(null);
    },
    onError: () => {
      message.error('Could not update interview');
    },
  });

  const submitInterview = useCallback(() => {
    if (!interviewApp) return;
    interviewMutation.mutate({
      appId: interviewApp.id,
      scheduledAt: interviewAt ? interviewAt.toISOString() : null,
      location: interviewLocation.trim() || null,
    });
  }, [interviewApp, interviewAt, interviewLocation, interviewMutation]);

  if (jobLoading) {
    return (
      <div className="leaderboard-skeleton">
        {[0, 1, 2, 3, 4].map((i) => (
          <div className="leaderboard-skeleton-row" key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="page-shell kanban-page-shell" style={{ gap: 16 }}>
      <div className="kanban-header" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {!isTopLevel && (
          <Button
            shape="circle"
            size="small"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(`/jobs/${jobId}`)}
            aria-label="Back to job"
          />
        )}

        {isTopLevel ? (
          <Select
            style={{ width: 280 }}
            placeholder="Select a job to view pipeline…"
            value={jobId}
            onChange={(val) => setSearchParams({ jobId: val })}
            options={jobs.map((j) => ({ value: j.id, label: j.title }))}
            showSearch
            filterOption={(input, option) =>
              String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        ) : (
          <div style={{ flex: 1 }}>
            <h1 className="page-title" style={{ fontSize: 20 }}>Pipeline</h1>
            <p className="page-description" style={{ margin: 0, fontSize: 13 }}>{job?.title}</p>
          </div>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <Button
            size="small"
            type={showTerminal ? 'default' : 'text'}
            icon={showTerminal ? <EyeOutlined /> : <EyeInvisibleOutlined />}
            onClick={() => setShowTerminal((v) => !v)}
          >
            {showTerminal ? 'Hide closed' : 'Show closed'}
          </Button>
          {jobId && (
            <Button
              size="small"
              icon={<TrophyOutlined />}
              onClick={() => navigate(`/jobs/${jobId}/leaderboard`)}
            >
              Leaderboard
            </Button>
          )}
        </div>
      </div>

      {!jobId && isTopLevel && (
        <div className="data-panel" style={{ textAlign: 'center', padding: '64px 24px' }}>
          <Empty description={<span style={{ color: 'var(--color-muted)' }}>Select a job above to view its pipeline</span>} />
        </div>
      )}

      {jobId && parsingSummary.total > 0 && (
        <div className="kanban-parsing-strip">
          <LoadingOutlined spin />
          <span>
            {parsingSummary.parsing} parsing, {parsingSummary.failed} failed — not yet on the board.
          </span>
        </div>
      )}

      <Modal
        title="Schedule Interview"
        open={!!interviewApp}
        onCancel={() => setInterviewApp(null)}
        onOk={submitInterview}
        okText="Save"
        confirmLoading={interviewMutation.isPending}
        destroyOnHidden
        footer={[
          <Button key="later" onClick={() => setInterviewApp(null)}>Add later</Button>,
          <Button key="save" type="primary" loading={interviewMutation.isPending} onClick={submitInterview}>Save</Button>,
        ]}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--color-muted)' }}>
            Time and place are optional — you can fill them in later from the candidate profile.
          </p>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-muted)', marginBottom: 4 }}>Date &amp; Time</div>
            <DatePicker
              showTime
              style={{ width: '100%' }}
              value={interviewAt}
              onChange={(val) => setInterviewAt(val)}
              format="YYYY-MM-DD HH:mm"
              disabledDate={(d) => !!d && d < dayjs().startOf('day')}
            />
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-muted)', marginBottom: 4 }}>Location / Link</div>
            <Input
              placeholder="Room 3A or https://meet.example.com/..."
              value={interviewLocation}
              onChange={(e) => setInterviewLocation(e.target.value)}
              maxLength={500}
            />
          </div>
          {interviewApp?.interview_scheduled_at && (
            <Button
              danger
              size="small"
              type="text"
              onClick={() => interviewMutation.mutate({ appId: interviewApp.id, scheduledAt: null, location: null })}
            >
              Clear interview
            </Button>
          )}
        </div>
      </Modal>

      {jobId && applications.length === 0 && !appsLoading ? (
        <div className="data-panel" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <Empty description={<span style={{ color: 'var(--color-muted)' }}>No applications yet</span>}>
            <Button type="primary" onClick={() => navigate(`/jobs/${jobId}`)}>Back to job</Button>
          </Empty>
        </div>
      ) : jobId ? (
        <div className={`kanban-board${!showTerminal ? ' kanban-board--fitted' : ''}`} role="list" aria-label="Candidate pipeline">
          {visibleColumns.map(({ status, label }) => {
            const items = groupedApplications[status] ?? EMPTY_GROUPS[status];
            const isTerminal = TERMINAL_COLUMNS.some((c) => c.status === status);
            return (
              <section
                key={status}
                className={`kanban-col col-${status}${dragOver === status ? ' is-over' : ''}${isTerminal ? ' is-terminal' : ''}`}
                role="listitem"
                onDragOver={isReadOnly ? undefined : (event) => {
                  event.preventDefault();
                  if (dragOver !== status) setDragOver(status);
                }}
                onDragLeave={isReadOnly ? undefined : (event) => {
                  if (event.currentTarget === event.target) setDragOver(null);
                }}
                onDrop={isReadOnly ? undefined : (event) => {
                  event.preventDefault();
                  handleDrop(status);
                }}
              >
                <div className="kanban-col-head">
                  <span>{label}</span>
                  <span className={`stage-chip stage-${status}`} style={{ height: 18, padding: '0 6px', fontSize: 10, fontWeight: 700 }}>
                    {items.length}
                  </span>
                </div>
                <div className="kanban-col-body">
                  {items.length === 0 ? (
                    <div className="kanban-col-empty">{isReadOnly ? 'Empty' : 'Drop here'}</div>
                  ) : (
                    items.map((app) => (
                      <PipelineCard
                        key={app.id}
                        app={app}
                        isDragging={draggingId === app.id}
                        isReadOnly={isReadOnly}
                        onDragStart={handleDragStart}
                        onDragEnd={handleDragEnd}
                        onMove={move}
                        onOpenCandidate={openCandidate}
                        onScheduleInterview={openInterviewModal}
                      />
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
