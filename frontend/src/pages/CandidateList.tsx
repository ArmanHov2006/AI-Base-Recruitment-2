import { useEffect, useMemo, useState } from 'react';
import {
  Table,
  Button,
  Tag,
  Space,
  Popconfirm,
  Empty,
  Pagination,
  message,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  deleteCandidate,
  searchCandidates,
} from '../api/candidates';
import UploadModal from '../components/UploadModal';
import SeniorityBadge from '../components/ui/SeniorityBadge';
import type { CandidateResponse, CandidateSearchFilters } from '../types';
import type { ColumnsType } from 'antd/es/table';

const PAGE_SIZE = 20;

const STAGE_FILTERS: { label: string; value: string | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Active', value: 'active' },
  { label: 'Hired', value: 'hired' },
  { label: 'Archived', value: 'archived' },
];

const LEVEL_FILTERS = [
  { label: 'All levels', value: undefined as string | undefined },
  { label: 'Junior', value: 'junior' },
  { label: 'Mid', value: 'mid' },
  { label: 'Senior', value: 'senior' },
  { label: 'Lead', value: 'lead' },
] as const;

const STAGE_DOT_COLOR: Record<string, string> = {
  Reviewing: '#a0aaff',
  Shortlisted: '#34d399',
  Interview: '#a0aaff',
  Offer: '#fbbf24',
  Hired: '#34d399',
};

const STATUS_STAGE_LABEL: Record<string, string> = {
  active: 'Reviewing',
  hired: 'Hired',
  archived: 'Archived',
};

function getInitials(value?: string | null): string {
  if (!value) return 'C';
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'C';
  return parts.slice(0, 2).map((p) => p[0]?.toUpperCase()).join('');
}

function formatTimeAgo(isoStr?: string | null): string {
  if (!isoStr) return '';
  const diff = Date.now() - new Date(isoStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function getScoreColor(score?: number | null): string {
  if (score === undefined || score === null) return 'var(--color-muted)';
  if (score >= 80) return '#34d399';
  if (score >= 60) return '#fbbf24';
  return '#f87171';
}

const AVATAR_PALETTE = [
  '#3d4acc', '#10b981', '#7c3aed', '#d97706', '#e11d48',
  '#0891b2', '#c2410c', '#15803d', '#7e22ce',
];
function candidateAvatarBg(id: string): string {
  const sum = id.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return AVATAR_PALETTE[sum % AVATAR_PALETTE.length];
}

function CandidateTableSkeleton() {
  return (
    <div className="table-skeleton" aria-label="Loading candidate rows">
      {[0, 1, 2, 3, 4].map((row) => (
        <div className="skeleton-row" key={row}>
          <div className="skeleton-line" style={{ width: '82%' }} />
          <div className="skeleton-line" style={{ width: `${64 + row * 5}%` }} />
          <div className="skeleton-line" style={{ width: '72%' }} />
          <div className="skeleton-line" style={{ width: '88%' }} />
        </div>
      ))}
    </div>
  );
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export default function CandidateList() {
  const [searchText, setSearchText] = useState('');
  const [skills] = useState<string[]>([]);
  const [seniority, setSeniority] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const debouncedQ = useDebounced(searchText, 300);

  const structuredFilters: CandidateSearchFilters = useMemo(
    () => ({
      q: debouncedQ || undefined,
      skills: skills.length > 0 ? skills : undefined,
      seniority: seniority || undefined,
      status: statusFilter,
      page,
      size: PAGE_SIZE,
    }),
    [debouncedQ, skills, seniority, statusFilter, page],
  );

  const { data, isFetching, isLoading } = useQuery({
    queryKey: ['candidates', 'search', structuredFilters],
    queryFn: () => searchCandidates(structuredFilters),
  });

  const candidates: CandidateResponse[] = data?.items ?? [];
  const total = data?.total ?? 0;

  const deleteMutation = useMutation({
    mutationFn: deleteCandidate,
    onSuccess: () => {
      message.success('Candidate deleted');
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
    },
  });

  useEffect(() => {
    setPage(1);
  }, [debouncedQ, skills, seniority, statusFilter]);

  const handleRowClick = (record: CandidateResponse) => {
    navigate(`/candidates/${record.id}`);
  };

  const columns: ColumnsType<CandidateResponse> = [
    {
      title: '#',
      key: 'rank',
      width: 48,
      render: (_, _record, index) => (
        <span style={{ color: '#64648a', fontFamily: 'Fira Code, monospace', fontSize: 13 }}>
          {(page - 1) * PAGE_SIZE + index + 1}
        </span>
      ),
    },
    {
      title: 'CANDIDATE',
      dataIndex: 'name',
      key: 'name',
      render: (name, record) => (
        <div className="entity-cell" style={{ gap: 10 }}>
          <div
            style={{
              display: 'grid',
              width: 36,
              height: 36,
              flexShrink: 0,
              placeItems: 'center',
              borderRadius: 9,
              background: candidateAvatarBg(record.id),
              color: '#fff',
              fontSize: 13,
              fontWeight: 800,
            }}
          >
            {getInitials(name || record.email)}
          </div>
          <div className="entity-copy">
            <strong style={{ fontSize: 14 }}>{name || 'Unnamed candidate'}</strong>
            <span style={{ fontSize: 12, color: '#64648a' }}>
              {record.location ? `${record.location} · ` : ''}
              {formatTimeAgo(record.created_at)}
            </span>
          </div>
        </div>
      ),
    },
    {
      title: 'ROLE',
      key: 'role',
      render: (_, record) => {
        const role = record.desired_position || record.work_experiences?.[0]?.role;
        return <span style={{ color: '#ededf5', fontSize: 14 }}>{role || '—'}</span>;
      },
    },
    {
      title: 'LEVEL',
      dataIndex: 'seniority',
      key: 'seniority',
      render: (s) => <SeniorityBadge seniority={s} size="sm" />,
    },
    {
      title: 'STAGE',
      dataIndex: 'status',
      key: 'stage',
      render: (status) => {
        const label = STATUS_STAGE_LABEL[status] || (status ?? '—');
        const dotColor = STAGE_DOT_COLOR[label] || '#64648a';
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: dotColor,
                flexShrink: 0,
                display: 'inline-block',
              }}
            />
            <span style={{ color: dotColor, fontSize: 13, fontWeight: 600 }}>{label}</span>
          </span>
        );
      },
    },
    {
      title: 'SKILLS',
      dataIndex: 'skills',
      key: 'skills',
      render: (skillList: string[]) => {
        if (!skillList || skillList.length === 0) return <span style={{ color: '#64648a' }}>—</span>;
        const display = skillList.slice(0, 2);
        const remaining = skillList.length - 2;
        return (
          <Space size={[4, 4]} wrap>
            {display.map((skill) => (
              <Tag className="skill-tag" key={skill} style={{ margin: 0 }}>{skill}</Tag>
            ))}
            {remaining > 0 && (
              <Tag className="skill-tag" style={{ margin: 0 }}>+{remaining}</Tag>
            )}
          </Space>
        );
      },
    },
    {
      title: 'EXP',
      dataIndex: 'years_experience',
      key: 'years_experience',
      render: (years) =>
        years !== undefined && years !== null ? (
          <span style={{ color: '#a1a1bb', fontFamily: 'Fira Code, monospace', fontSize: 13 }}>
            {years}y
          </span>
        ) : (
          <span style={{ color: '#64648a' }}>—</span>
        ),
    },
    {
      title: 'FIT ↓',
      key: 'fit',
      width: 64,
      render: (_, record) => {
        const score = (record as CandidateResponse & { fit_score?: number }).fit_score;
        if (score === undefined || score === null) {
          return <span style={{ color: '#64648a', fontFamily: 'Fira Code, monospace' }}>—</span>;
        }
        return (
          <span
            style={{
              color: getScoreColor(score),
              fontFamily: 'Fira Code, monospace',
              fontSize: 15,
              fontWeight: 700,
            }}
          >
            {score}
          </span>
        );
      },
    },
    {
      title: '',
      key: 'actions',
      width: 40,
      render: (_, record) => (
        <Popconfirm
          title="Delete candidate?"
          onConfirm={(e) => { e?.stopPropagation(); deleteMutation.mutate(record.id); }}
          onCancel={(e) => e?.stopPropagation()}
          okText="Yes"
          cancelText="No"
        >
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            size="small"
            onClick={(e) => e.stopPropagation()}
            loading={deleteMutation.isPending && deleteMutation.variables === record.id}
            aria-label={`Delete ${record.name || 'candidate'}`}
          />
        </Popconfirm>
      ),
    },
  ];

  const emptyState = (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No candidates yet">
      <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadModalOpen(true)}>
        Upload your first resume
      </Button>
    </Empty>
  );

  return (
    <div className="page-shell">
      {/* Filter bar */}
      <div className="clist-filter-bar">
        <div className="clist-search-wrap">
          <SearchOutlined style={{ color: '#64648a', flexShrink: 0 }} />
          <input
            className="clist-search-input"
            placeholder="Filter by name, role, skill..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            aria-label="Search candidates"
          />
        </div>

        <div className="clist-pill-group">
          {STAGE_FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={`clist-pill${statusFilter === f.value ? ' is-active' : ''}`}
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="clist-pill-divider" />

        <div className="clist-pill-group">
          {LEVEL_FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={`clist-pill${seniority === f.value && (f.value !== undefined || seniority === undefined) ? ' is-active' : ''}`}
              onClick={() => setSeniority(seniority === f.value ? undefined : f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <span className="clist-count">{total} candidates</span>
      </div>

      {/* Table */}
      <div className="data-panel">
        {isLoading ? (
          <CandidateTableSkeleton />
        ) : (
          <>
            <Table
              className="premium-table clist-table"
              columns={columns}
              dataSource={candidates}
              rowKey="id"
              loading={isFetching && !isLoading}
              pagination={false}
              onRow={(record) => ({
                onClick: () => handleRowClick(record),
                style: { cursor: 'pointer' },
              })}
              locale={{ emptyText: candidates.length === 0 ? emptyState : undefined }}
              scroll={candidates.length > 0 ? { x: 'max-content' } : undefined}
            />

            {total > PAGE_SIZE && (
              <div className="panel-pagination">
                <Pagination
                  current={page}
                  pageSize={PAGE_SIZE}
                  total={total}
                  onChange={setPage}
                  showSizeChanger={false}
                  showTotal={(t) => `${t} candidates`}
                />
              </div>
            )}
          </>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setUploadModalOpen(true)}
        >
          Upload Resume
        </Button>
      </div>

      <UploadModal
        open={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
      />
    </div>
  );
}
