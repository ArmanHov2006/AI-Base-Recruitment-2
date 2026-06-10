import { useState } from 'react';
import {
  Button,
  Col,
  DatePicker,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import { listAuditLogs, listBusinessEvents } from '../api/audit';
import type { AuditLogEntry, BusinessEventEntry } from '../types';

const { RangePicker } = DatePicker;

const PAGE_SIZE = 50;

const METHOD_OPTIONS = ['GET', 'POST', 'PATCH', 'PUT', 'DELETE'].map((m) => ({
  label: m,
  value: m,
}));

const METHOD_COLOR: Record<string, string> = {
  GET: 'blue',
  POST: 'green',
  PATCH: 'orange',
  PUT: 'gold',
  DELETE: 'red',
};

function statusColor(code: number): string {
  if (code < 300) return 'success';
  if (code < 400) return 'warning';
  return 'error';
}

function formatTs(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(iso));
}

function JsonDiffModal({
  open,
  event,
  onClose,
}: {
  open: boolean;
  event: BusinessEventEntry | null;
  onClose: () => void;
}) {
  if (!event) return null;
  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={
        <span>
          <Tag>{event.action}</Tag> {event.resource_type} — diff
        </span>
      }
      width={760}
      destroyOnHidden
    >
      <Row gutter={16}>
        <Col span={12}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Before
          </Typography.Text>
          <pre
            style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid var(--color-line)',
              color: 'var(--color-ink)',
              padding: 12,
              borderRadius: 6,
              fontSize: 12,
              overflow: 'auto',
              maxHeight: 480,
              marginTop: 4,
            }}
          >
            {event.before ? JSON.stringify(event.before, null, 2) : '—'}
          </pre>
        </Col>
        <Col span={12}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            After
          </Typography.Text>
          <pre
            style={{
              background: 'rgba(52,211,153,0.08)',
              border: '1px solid rgba(52,211,153,0.2)',
              color: 'var(--color-ink)',
              padding: 12,
              borderRadius: 6,
              fontSize: 12,
              overflow: 'auto',
              maxHeight: 480,
              marginTop: 4,
            }}
          >
            {event.after ? JSON.stringify(event.after, null, 2) : '—'}
          </pre>
        </Col>
      </Row>
      {event.meta && (
        <>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12 }}>
            Meta
          </Typography.Text>
          <pre
            style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid var(--color-line)',
              color: 'var(--color-ink)',
              padding: 12,
              borderRadius: 6,
              fontSize: 12,
              overflow: 'auto',
              maxHeight: 200,
              marginTop: 4,
            }}
          >
            {JSON.stringify(event.meta, null, 2)}
          </pre>
        </>
      )}
    </Modal>
  );
}

function HttpLogTab() {
  const [page, setPage] = useState(1);
  const [method, setMethod] = useState<string | undefined>();
  const [pathContains, setPathContains] = useState('');
  const [pathInput, setPathInput] = useState('');
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);

  const params = {
    method: method || undefined,
    path_contains: pathContains || undefined,
    from_dt: dateRange?.[0] || undefined,
    to_dt: dateRange?.[1] || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['audit', 'http', params],
    queryFn: () => listAuditLogs(params),
  });

  const columns: ColumnsType<AuditLogEntry> = [
    {
      title: 'Time',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => <span style={{ fontSize: 12, color: '#6B7280' }}>{formatTs(v)}</span>,
    },
    {
      title: 'Method',
      dataIndex: 'method',
      key: 'method',
      width: 90,
      render: (v: string) => <Tag color={METHOD_COLOR[v] || 'default'}>{v}</Tag>,
    },
    {
      title: 'Path',
      dataIndex: 'path',
      key: 'path',
      render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code>,
    },
    {
      title: 'Status',
      dataIndex: 'status_code',
      key: 'status_code',
      width: 80,
      render: (v: number) => <Tag color={statusColor(v)}>{v}</Tag>,
    },
    {
      title: 'IP',
      dataIndex: 'ip',
      key: 'ip',
      width: 130,
      render: (v: string | null) => (
        <span style={{ fontSize: 12, color: '#9CA3AF' }}>{v ?? '—'}</span>
      ),
    },
    {
      title: 'User',
      key: 'user',
      width: 220,
      render: (_: unknown, r: AuditLogEntry) => {
        const label = ((r as AuditLogEntry & { user_full_name?: string; user_email?: string }).user_full_name
          || (r as AuditLogEntry & { user_email?: string }).user_email
          || (r as AuditLogEntry).user_id?.slice(0, 8)) ?? null;
        return (
          <span style={{ fontSize: 12, color: '#9CA3AF' }}>
            {label ?? <em>anon</em>}
          </span>
        );
      },
    },
    {
      title: 'Request ID',
      dataIndex: 'request_id',
      key: 'request_id',
      width: 220,
      render: (v: string) => (
        <span style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'monospace' }}>{v}</span>
      ),
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="Method"
          options={METHOD_OPTIONS}
          value={method}
          onChange={(v) => { setMethod(v); setPage(1); }}
          style={{ width: 110 }}
        />
        <Input
          placeholder="Path contains…"
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          onPressEnter={() => { setPathContains(pathInput); setPage(1); }}
          suffix={
            <SearchOutlined
              style={{ cursor: 'pointer', color: '#6B7280' }}
              onClick={() => { setPathContains(pathInput); setPage(1); }}
            />
          }
          style={{ width: 220 }}
          allowClear
          onClear={() => { setPathInput(''); setPathContains(''); setPage(1); }}
        />
        <RangePicker
          showTime
          onChange={(_, strs) => {
            setDateRange(strs[0] && strs[1] ? [strs[0], strs[1]] : null);
            setPage(1);
          }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching}>
          Refresh
        </Button>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: data?.total ?? 0,
          onChange: (p) => setPage(p),
          showTotal: (t) => `${t} entries`,
          showSizeChanger: false,
        }}
        size="small"
        scroll={{ x: 1100 }}
        locale={{ emptyText: 'No entries' }}
      />
    </div>
  );
}

const RESOURCE_TYPE_OPTIONS = [
  'job', 'candidate', 'application', 'evaluation', 'note', 'user', 'invite', 'comparison',
].map((r) => ({ label: r, value: r }));

const ACTION_OPTIONS = [
  'job.created', 'job.updated', 'job.deleted',
  'candidate.created', 'candidate.updated', 'candidate.deleted',
  'application.submitted', 'application.status_changed', 'application.deleted', 'application.stage_transitioned',
  'evaluation.created', 'evaluation.updated', 'evaluation.deleted',
  'note.created', 'note.updated', 'note.deleted',
  'comparison.created', 'comparison.analyzed',
  'user.role_changed', 'user.active_changed', 'user.registered', 'user.password_changed',
  'invite.created', 'invite.revoked',
].map((a) => ({ label: a, value: a }));

function BusinessEventsTab() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<string | undefined>();
  const [resourceType, setResourceType] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [diffEvent, setDiffEvent] = useState<BusinessEventEntry | null>(null);

  const params = {
    action: action || undefined,
    resource_type: resourceType || undefined,
    from_dt: dateRange?.[0] || undefined,
    to_dt: dateRange?.[1] || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['audit', 'events', params],
    queryFn: () => listBusinessEvents(params),
  });

  const columns: ColumnsType<BusinessEventEntry> = [
    {
      title: 'Time',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => <span style={{ fontSize: 12, color: '#6B7280' }}>{formatTs(v)}</span>,
    },
    {
      title: 'Action',
      dataIndex: 'action',
      key: 'action',
      width: 220,
      render: (v: string) => <Tag color="geekblue">{v}</Tag>,
    },
    {
      title: 'Resource',
      key: 'resource',
      width: 120,
      render: (_: unknown, r: BusinessEventEntry) => <Tag>{r.resource_type}</Tag>,
    },
    {
      title: 'Resource ID',
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 220,
      render: (v: string) => (
        <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#6B7280' }}>{v}</span>
      ),
    },
    {
      title: 'Actor',
      key: 'actor',
      width: 220,
      render: (_: unknown, r: BusinessEventEntry) => {
        const label = ((r as BusinessEventEntry & { actor_full_name?: string; actor_email?: string }).actor_full_name
          || (r as BusinessEventEntry & { actor_email?: string }).actor_email
          || (r as BusinessEventEntry).actor_id?.slice(0, 8)) ?? null;
        return (
          <span style={{ fontSize: 12, color: '#9CA3AF' }}>
            {label ?? <em>system</em>}
          </span>
        );
      },
    },
    {
      title: 'Diff',
      key: 'diff',
      width: 80,
      render: (_: unknown, r: BusinessEventEntry) =>
        r.before || r.after ? (
          <Button type="link" size="small" onClick={() => setDiffEvent(r)}>
            View
          </Button>
        ) : (
          <span style={{ color: '#D1D5DB' }}>—</span>
        ),
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="Action"
          options={ACTION_OPTIONS}
          value={action}
          onChange={(v) => { setAction(v); setPage(1); }}
          style={{ width: 240 }}
          showSearch
        />
        <Select
          allowClear
          placeholder="Resource type"
          options={RESOURCE_TYPE_OPTIONS}
          value={resourceType}
          onChange={(v) => { setResourceType(v); setPage(1); }}
          style={{ width: 150 }}
        />
        <RangePicker
          showTime
          onChange={(_, strs) => {
            setDateRange(strs[0] && strs[1] ? [strs[0], strs[1]] : null);
            setPage(1);
          }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching}>
          Refresh
        </Button>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: data?.total ?? 0,
          onChange: (p) => setPage(p),
          showTotal: (t) => `${t} events`,
          showSizeChanger: false,
        }}
        size="small"
        scroll={{ x: 1000 }}
        locale={{ emptyText: 'No events' }}
        onRow={(r) => ({
          style: { cursor: r.before || r.after ? 'pointer' : 'default' },
          onClick: () => { if (r.before || r.after) setDiffEvent(r); },
        })}
      />

      <JsonDiffModal
        open={!!diffEvent}
        event={diffEvent}
        onClose={() => setDiffEvent(null)}
      />
    </div>
  );
}

export default function AuditLog() {
  const { user } = useAuth();

  if (user?.role !== 'admin') {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Typography.Title level={4}>Access Denied</Typography.Title>
        <p>Admin role required to view audit logs.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit Log</h1>
          <p className="page-description">HTTP write log and semantic business events.</p>
        </div>
      </div>

      <Tabs
        items={[
          { key: 'http', label: 'HTTP Log', children: <HttpLogTab /> },
          { key: 'events', label: 'Business Events', children: <BusinessEventsTab /> },
        ]}
      />
    </div>
  );
}
