import { useState } from 'react';
import {
  Card,
  Tag,
  Button,
  Skeleton,
  Select,
  Tabs,
  List,
  Popconfirm,
  Empty,
  Space,
  Spin,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  MailOutlined,
  PhoneOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  SwapOutlined,
  TrophyOutlined,
  PartitionOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { getJob } from '../api/jobs';
import {
  listApplications,
  bulkCreateApplications,
  updateApplicationStatus,
  deleteApplication,
} from '../api/applications';
import { uploadFile } from '../api/files';
import StepUpload from '../components/UploadModal/StepUpload';
import { APPLICATION_STATUSES, USER_SETTABLE_STATUSES } from '../types';
import type { ApplicationStatus, JobApplication, UserSettableStatus } from '../types';

const seniorityColorMap: Record<string, string> = {
  junior: 'green',
  mid: 'blue',
  senior: 'orange',
  lead: 'purple',
};

const statusColorMap: Record<ApplicationStatus, string> = {
  parsing: 'default',
  parse_failed: 'red',
  applied: 'blue',
  reviewing: 'geekblue',
  shortlisted: 'cyan',
  screening: 'cyan',
  interview: 'gold',
  offer: 'purple',
  hired: 'green',
  rejected: 'red',
  withdrawn: 'default',
};

const statusLabel = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ');

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadKey, setUploadKey] = useState(0);
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null);

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['job', id],
    queryFn: () => getJob(id!),
    enabled: !!id,
  });

  const { data: applications = [], isLoading: appsLoading } = useQuery({
    queryKey: ['applications', id],
    queryFn: () => listApplications(id!),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data?.some((a) => a.status === 'parsing') ? 2000 : false,
  });

  const statusMutation = useMutation({
    mutationFn: ({ appId, status }: { appId: string; status: UserSettableStatus }) =>
      updateApplicationStatus(id!, appId, status),
    onSuccess: () => {
      message.success('Status updated');
      queryClient.invalidateQueries({ queryKey: ['applications', id] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (appId: string) => deleteApplication(id!, appId),
    onSuccess: () => {
      message.success('Application removed');
      queryClient.invalidateQueries({ queryKey: ['applications', id] });
    },
  });

  const handleUpload = async (files: File[]) => {
    if (!id || files.length === 0) return;
    setIsProcessing(true);
    setUploadProgress({ done: 0, total: files.length });
    try {
      const UPLOAD_BATCH = 20;
      const fileIds: string[] = [];
      let done = 0;
      for (let i = 0; i < files.length; i += UPLOAD_BATCH) {
        const batch = files.slice(i, i + UPLOAD_BATCH);
        const uploads = await Promise.all(batch.map(uploadFile));
        fileIds.push(...uploads.map((u) => u.file_id));
        done += batch.length;
        setUploadProgress({ done, total: files.length });
      }
      await bulkCreateApplications(id, fileIds);
      const n = files.length;
      message.success(`${n} resume${n > 1 ? 's' : ''} uploaded — parsing in background`);
      queryClient.invalidateQueries({ queryKey: ['applications', id] });
      setUploadKey((k) => k + 1);
    } catch {
      // apiClient interceptor already toasted the error
    } finally {
      setIsProcessing(false);
      setUploadProgress(null);
    }
  };

  if (jobLoading) {
    return (
      <div>
        <Skeleton.Button active size="small" style={{ width: 120, marginBottom: 24 }} />
        <Card>
          <Skeleton active paragraph={{ rows: 4 }} />
        </Card>
      </div>
    );
  }

  if (!job) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <p>Job not found</p>
        <Button onClick={() => navigate('/jobs')}>Back to Jobs</Button>
      </div>
    );
  }

  const grouped = USER_SETTABLE_STATUSES.map((status) => ({
    status,
    items: applications.filter((a) => a.status === status),
  }));

  const renderApplicationItem = (app: JobApplication) => {
    if (app.status === 'parsing') {
      return (
        <List.Item
          key={app.id}
          actions={[
            <Tag key="status" color={statusColorMap.parsing} icon={<LoadingOutlined spin />}>
              Parsing
            </Tag>,
          ]}
        >
          <List.Item.Meta
            avatar={<Spin indicator={<LoadingOutlined spin />} />}
            title="Parsing resume…"
            description="Extracting candidate data via LLM"
          />
        </List.Item>
      );
    }

    if (app.status === 'parse_failed') {
      return (
        <List.Item
          key={app.id}
          actions={[
            <Tag key="status" color={statusColorMap.parse_failed} icon={<ExclamationCircleOutlined />}>
              Failed
            </Tag>,
            <Popconfirm
              key="delete"
              title="Remove application"
              description="Soft-delete this failed application?"
              onConfirm={() => deleteMutation.mutate(app.id)}
            >
              <Button type="text" danger size="small" icon={<DeleteOutlined />} />
            </Popconfirm>,
          ]}
        >
          <List.Item.Meta
            title="Parse failed"
            description={app.error_message || 'Unknown error'}
          />
        </List.Item>
      );
    }

    return (
      <List.Item
        key={app.id}
        actions={[
          <Select
            key="status"
            size="small"
            value={app.status as UserSettableStatus}
            style={{ width: 130 }}
            onClick={(e) => e.stopPropagation()}
            onChange={(value) =>
              statusMutation.mutate({ appId: app.id, status: value as UserSettableStatus })
            }
            options={USER_SETTABLE_STATUSES.map((s) => ({ value: s, label: statusLabel(s) }))}
          />,
          <Popconfirm
            key="delete"
            title="Remove application"
            description="Soft-delete this application?"
            onConfirm={(e) => {
              e?.stopPropagation();
              deleteMutation.mutate(app.id);
            }}
            onCancel={(e) => e?.stopPropagation()}
          >
            <Button
              type="text"
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={(e) => e.stopPropagation()}
            />
          </Popconfirm>,
        ]}
        style={{ cursor: app.candidate_id ? 'pointer' : 'default' }}
        onClick={() => app.candidate_id && navigate(`/candidates/${app.candidate_id}`)}
      >
        <List.Item.Meta
          title={app.candidate?.name || 'Unknown'}
          description={
            <Space size="middle" wrap>
              {app.candidate?.email && (
                <span>
                  <MailOutlined style={{ color: '#999', marginRight: 4 }} />
                  {app.candidate.email}
                </span>
              )}
              {app.candidate?.phone && (
                <span>
                  <PhoneOutlined style={{ color: '#999', marginRight: 4 }} />
                  {app.candidate.phone}
                </span>
              )}
              <span style={{ color: '#999' }}>
                applied {new Date(app.applied_at).toLocaleDateString()}
              </span>
            </Space>
          }
        />
      </List.Item>
    );
  };

  const allTab = {
    key: 'all',
    label: `All (${applications.length})`,
    children: applications.length === 0 ? (
      <Empty description="No applications yet" />
    ) : (
      <List
        dataSource={applications}
        renderItem={renderApplicationItem}
        loading={appsLoading}
      />
    ),
  };

  const statusTabs = grouped.map(({ status, items }) => ({
    key: status,
    label: (
      <span>
        <Tag color={statusColorMap[status]} style={{ marginRight: 4 }}>
          {items.length}
        </Tag>
        {statusLabel(status)}
      </span>
    ),
    children: items.length === 0 ? (
      <Empty description={`No ${status} applications`} />
    ) : (
      <List dataSource={items} renderItem={renderApplicationItem} />
    ),
  }));

  // Silence unused-warning for APPLICATION_STATUSES (kept exported for callers)
  void APPLICATION_STATUSES;

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', gap: 8 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/jobs')}>
          Back to Jobs
        </Button>
        <Button
          icon={<TrophyOutlined />}
          onClick={() => navigate(`/jobs/${id}/leaderboard`)}
        >
          Leaderboard
        </Button>
        <Button
          icon={<PartitionOutlined />}
          onClick={() => navigate(`/jobs/${id}/pipeline`)}
        >
          Pipeline
        </Button>
        <Button
          icon={<BarChartOutlined />}
          onClick={() => navigate(`/jobs/${id}/role-analytics`)}
        >
          Role Analytics
        </Button>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ flex: 1, minWidth: 280 }}>
            <h1 style={{ margin: '0 0 8px 0', fontSize: 24 }}>{job.title}</h1>
            <Space wrap>
              {job.required_seniority && (
                <Tag color={seniorityColorMap[job.required_seniority] || 'default'}>
                  {statusLabel(job.required_seniority)}
                </Tag>
              )}
              {job.location && <span style={{ color: '#666' }}>{job.location}</span>}
            </Space>
          </div>
          <div>
            {applications.filter((a: JobApplication) => a.candidate_id).length >= 2 && (
              <Button icon={<SwapOutlined />} onClick={() => navigate(`/jobs/${job.id}/compare`)}>
                Compare Candidates
              </Button>
            )}
          </div>
        </div>
        {job.required_skills && job.required_skills.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <strong style={{ marginRight: 8 }}>Required skills:</strong>
            <Space size={[0, 4]} wrap>
              {job.required_skills.map((s) => (
                <Tag key={s} color="blue">
                  {s}
                </Tag>
              ))}
            </Space>
          </div>
        )}
        {job.description && (
          <p style={{ marginTop: 16, whiteSpace: 'pre-wrap', color: '#444' }}>{job.description}</p>
        )}
      </Card>

      <Card title="Upload Resume to Apply" style={{ marginBottom: 24 }}>
        <StepUpload key={uploadKey} onUploadComplete={handleUpload} isUploading={isProcessing} multiple uploadProgress={uploadProgress} />
      </Card>

      <Card title={`Applications (${applications.length})`}>
        <Tabs items={[allTab, ...statusTabs]} />
      </Card>
    </div>
  );
}
