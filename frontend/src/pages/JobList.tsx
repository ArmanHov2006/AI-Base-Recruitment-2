import { useState, useMemo, useEffect } from 'react';
import {
  Table,
  Input,
  Button,
  Tag,
  Space,
  Popconfirm,
  Empty,
  message,
  Modal,
  Form,
  Select,
  Avatar,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { listJobs, createJob, deleteJob, generateJobDescription } from '../api/jobs';
import type { JobResponse, CreateJobRequest } from '../types';
import type { ColumnsType } from 'antd/es/table';

const seniorityColorMap: Record<string, string> = {
  junior: 'green',
  mid: 'blue',
  senior: 'orange',
  lead: 'purple',
};

const seniorityOptions = [
  { value: 'junior', label: 'Junior' },
  { value: 'mid', label: 'Mid' },
  { value: 'senior', label: 'Senior' },
  { value: 'lead', label: 'Lead' },
];

function getInitials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'J';
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('');
}

function formatDate(value?: string | null): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(
    new Date(value),
  );
}

export default function JobList() {
  const [searchText, setSearchText] = useState('');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [form] = Form.useForm<CreateJobRequest>();

  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  useEffect(() => {
    if ((location.state as { openCreate?: boolean } | null)?.openCreate) {
      setCreateModalOpen(true);
      window.history.replaceState({}, '');
    }
  }, [location.state]);

  useEffect(() => {
    if (searchParams.get('create') === 'true') {
      setCreateModalOpen(true);
      setSearchParams({}, { replace: true });
    }
  }, []);

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
  });

  const createMutation = useMutation({
    mutationFn: createJob,
    onSuccess: () => {
      message.success('Job created');
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      setCreateModalOpen(false);
      form.resetFields();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteJob,
    onSuccess: () => {
      message.success('Job deleted');
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) =>
      !searchText ||
      job.title.toLowerCase().includes(searchText.toLowerCase()) ||
      job.location?.toLowerCase().includes(searchText.toLowerCase())
    );
  }, [jobs, searchText]);

  const skillCoverage = useMemo(() => {
    const uniqueSkills = new Set<string>();
    jobs.forEach((job) => job.required_skills?.forEach((skill) => uniqueSkills.add(skill)));
    return uniqueSkills.size;
  }, [jobs]);

  const seniorRoles = useMemo(() => {
    return jobs.filter((job) => ['senior', 'lead'].includes(job.required_seniority ?? '')).length;
  }, [jobs]);

  const handleGenerate = async () => {
    const values = form.getFieldsValue();
    const title = values.title?.trim();
    const seniority = values.required_seniority?.trim();
    if (!title || !seniority) {
      message.warning('Fill in Title and Seniority before generating a description.');
      return;
    }
    setGenerateLoading(true);
    try {
      const draft = await generateJobDescription({
        title,
        seniority,
        required_skills: values.required_skills ?? [],
        notes: undefined,
      });
      // Format the draft into the description field
      const lines: string[] = [];
      if (draft.summary) {
        lines.push(draft.summary, '');
      }
      if (draft.responsibilities.length > 0) {
        lines.push('Responsibilities:');
        draft.responsibilities.forEach((r) => lines.push(`- ${r}`));
        lines.push('');
      }
      if (draft.requirements.length > 0) {
        lines.push('Requirements:');
        draft.requirements.forEach((r) => lines.push(`- ${r}`));
      }
      form.setFieldsValue({ description: lines.join('\n') });
      message.success('Description generated — review and edit before saving.');
    } catch {
      message.error('Failed to generate description. Check that Title and Seniority are filled in.');
    } finally {
      setGenerateLoading(false);
    }
  };

  const handleCreate = async () => {
    const values = await form.validateFields();
    createMutation.mutate(values);
  };

  const columns: ColumnsType<JobResponse> = [
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      render: (title, record) => (
        <div className="entity-cell">
          <Avatar className="entity-avatar" size={38}>
            {getInitials(title)}
          </Avatar>
          <div className="job-title-cell">
            <strong>{title}</strong>
            <span>{record.location || 'Location not set'}</span>
          </div>
        </div>
      ),
    },
    {
      title: 'Seniority',
      dataIndex: 'required_seniority',
      key: 'required_seniority',
      render: (seniority) =>
        seniority ? (
          <Tag color={seniorityColorMap[seniority] || 'default'}>
            {seniority.charAt(0).toUpperCase() + seniority.slice(1)}
          </Tag>
        ) : '-',
    },
    {
      title: 'Required Skills',
      dataIndex: 'required_skills',
      key: 'required_skills',
      render: (skills: string[]) => {
        if (!skills || skills.length === 0) return '-';
        const display = skills.slice(0, 4);
        const remaining = skills.length - 4;
        return (
          <Space size={[0, 4]} wrap>
            {display.map((skill) => (
              <Tag className="skill-tag" key={skill}>{skill}</Tag>
            ))}
            {remaining > 0 && <Tag>+{remaining} more</Tag>}
          </Space>
        );
      },
    },
    {
      title: 'Location',
      dataIndex: 'location',
      key: 'location',
      render: (location) => (location ? <span className="location-chip">{location}</span> : '-'),
    },
    {
      title: 'Created At',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date) => <span className="cell-muted">{formatDate(date)}</span>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 80,
      render: (_, record) => (
        <Popconfirm
          title="Delete job"
          description="Are you sure you want to delete this job posting?"
          onConfirm={(e) => {
            e?.stopPropagation();
            deleteMutation.mutate(record.id);
          }}
          onCancel={(e) => e?.stopPropagation()}
          okText="Yes"
          cancelText="No"
        >
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={(e) => e.stopPropagation()}
            loading={deleteMutation.isPending && deleteMutation.variables === record.id}
            aria-label={`Delete ${record.title}`}
          />
        </Popconfirm>
      ),
    },
  ];

  const emptyState = (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No job postings yet">
      <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
        Create your first job
      </Button>
    </Empty>
  );

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <h1 className="page-title">Jobs</h1>
          <p className="page-description">
            Role requirements, seniority, and skill signals.
          </p>
        </div>
        <div className="page-actions">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
            aria-label="Create job"
          >
            Create Job
          </Button>
        </div>
      </div>

      <div className="metric-strip">
        <div className="metric-tile">
          <span>Open roles</span>
          <strong>{jobs.length}</strong>
          <small>Jobs in the workspace</small>
        </div>
        <div className="metric-tile">
          <span>Search results</span>
          <strong>{filteredJobs.length}</strong>
          <small>Roles matching the current query</small>
        </div>
        <div className="metric-tile">
          <span>Critical roles</span>
          <strong>{seniorRoles}</strong>
          <small>Senior and lead positions</small>
        </div>
        <div className="metric-tile">
          <span>Skill signals</span>
          <strong>{skillCoverage}</strong>
          <small>Unique required skills</small>
        </div>
      </div>

      <div className="filter-panel">
        <div className="filter-row">
          <Input
            placeholder="Search by title or location"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="search-field"
            allowClear
            aria-label="Search jobs"
          />
        </div>
      </div>

      <div className="data-panel">
        <div className="data-panel-header">
          <div>
            <h2>Role library</h2>
            <span>
              {filteredJobs.length} role{filteredJobs.length === 1 ? '' : 's'} found
            </span>
          </div>
          <Tag color="blue">{searchText ? 'Filtered' : 'All roles'}</Tag>
        </div>

        <Table
          className="premium-table"
          columns={columns}
          dataSource={filteredJobs}
          rowKey="id"
          loading={isLoading}
          onRow={(record) => ({
            onClick: () => navigate(`/jobs/${record.id}`),
            style: { cursor: 'pointer' },
          })}
          locale={{
            emptyText: !isLoading && jobs.length === 0 ? emptyState : undefined,
          }}
          scroll={{ x: 'max-content' }}
        />
      </div>

      <Modal
        title="Create Job Posting"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false);
          form.resetFields();
        }}
        confirmLoading={createMutation.isPending}
        okText="Create"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="Title" rules={[{ required: true, message: 'Title is required' }]}>
            <Input placeholder="e.g. Senior Backend Engineer" />
          </Form.Item>
          <Form.Item name="required_seniority" label="Seniority">
            <Select placeholder="Select seniority" options={seniorityOptions} allowClear />
          </Form.Item>
          <Form.Item name="location" label="Location">
            <Input placeholder="e.g. Yerevan, Armenia" />
          </Form.Item>
          <Form.Item name="required_skills" label="Required Skills">
            <Select
              mode="tags"
              placeholder="Type and press Enter to add skills"
              tokenSeparators={[',']}
            />
          </Form.Item>
          <Form.Item
            name="description"
            label={
              <span>
                Description{' '}
                <Tooltip title="Fill in Title and Seniority, then click Generate to draft a description with the AI.">
                  <Button
                    size="small"
                    type="dashed"
                    icon={<ThunderboltOutlined />}
                    loading={generateLoading}
                    onClick={handleGenerate}
                    style={{ marginLeft: 8 }}
                  >
                    Generate
                  </Button>
                </Tooltip>
              </span>
            }
          >
            <Input.TextArea rows={5} placeholder="Job description (or click Generate to draft with AI)..." />
          </Form.Item>
          <Form.Item name="threshold_score" label="Score Threshold (0–10)" tooltip="Minimum score for a candidate to qualify in Role Analytics">
            <Input type="number" min={0} max={10} step={0.5} placeholder="e.g. 7.5" />
          </Form.Item>
          <Form.Item name="candidates_for_next_stage" label="Interview Target" tooltip="How many qualified candidates you want before moving to interviews">
            <Input type="number" min={1} step={1} placeholder="e.g. 30" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
