import { useState } from 'react';
import {
  Card,
  Button,
  Modal,
  Form,
  Select,
  Input,
  Rate,
  Collapse,
  InputNumber,
  Tag,
  Skeleton,
  Empty,
  Popconfirm,
  message,
  Space,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listEvaluations,
  createEvaluation,
  deleteEvaluation,
} from '../../api/evaluations';
import { listJobs } from '../../api/jobs';
import { useAuth } from '../../context/AuthContext';
import {
  EVALUATION_STAGES,
  type CreateEvaluationRequest,
  type EvaluationStage,
} from '../../types';

const STAGE_COLORS: Record<string, string> = {
  reviewing: 'blue',
  shortlisted: 'cyan',
  interview: 'geekblue',
  offer: 'gold',
  hired: 'green',
  rejected: 'red',
};

const STAGE_LABELS: Record<string, string> = {
  reviewing: 'Reviewing',
  shortlisted: 'Shortlisted',
  interview: 'Interview',
  offer: 'Offer',
  hired: 'Hired',
  rejected: 'Rejected',
};

interface EvaluationFormValues {
  job_id: string;
  stage: EvaluationStage;
  overall_rating?: number;
  feedback?: string;
  technical_score?: number;
  communication_score?: number;
  leadership_score?: number;
  cultural_fit_score?: number;
  english_score?: number;
  domain_score?: number;
}

export default function EvaluationsSection({ candidateId }: { candidateId: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<EvaluationFormValues>();

  const { data: evaluations = [], isLoading } = useQuery({
    queryKey: ['candidate', candidateId, 'evaluations'],
    queryFn: () => listEvaluations(candidateId),
  });

  const { data: jobs = [] } = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    enabled: modalOpen,
  });

  const createMutation = useMutation({
    mutationFn: (body: CreateEvaluationRequest) => createEvaluation(candidateId, body),
    onSuccess: () => {
      message.success('Evaluation added');
      queryClient.invalidateQueries({ queryKey: ['candidate', candidateId, 'evaluations'] });
      setModalOpen(false);
      form.resetFields();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (evalId: string) => deleteEvaluation(candidateId, evalId),
    onSuccess: () => {
      message.success('Evaluation deleted');
      queryClient.invalidateQueries({ queryKey: ['candidate', candidateId, 'evaluations'] });
    },
  });

  const handleSubmit = (values: EvaluationFormValues) => {
    const body: CreateEvaluationRequest = {
      job_id: values.job_id,
      stage: values.stage,
      overall_rating: values.overall_rating ?? null,
      feedback: values.feedback ?? null,
      technical_score: values.technical_score ?? null,
      communication_score: values.communication_score ?? null,
      leadership_score: values.leadership_score ?? null,
      cultural_fit_score: values.cultural_fit_score ?? null,
      english_score: values.english_score ?? null,
      domain_score: values.domain_score ?? null,
    };
    createMutation.mutate(body);
  };

  return (
    <Card
      title="Evaluations"
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalOpen(true)}
        >
          Add Evaluation
        </Button>
      }
      style={{ marginBottom: 16 }}
    >
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : evaluations.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No evaluations yet" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {evaluations.map((ev) => {
            const canDelete = user?.id === ev.evaluator_id;
            return (
              <Card key={ev.id} size="small" type="inner">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: 8,
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  <Space size={12} wrap>
                    <Tag color={STAGE_COLORS[ev.stage] || 'default'}>
                      {STAGE_LABELS[ev.stage] || ev.stage}
                    </Tag>
                    {ev.overall_rating !== null && (
                      <Rate disabled value={ev.overall_rating} style={{ fontSize: 14 }} />
                    )}
                    <span style={{ fontSize: 12, color: '#a1a1bb' }}>
                      {ev.evaluator_name || 'Unknown evaluator'} ·{' '}
                      {new Date(ev.created_at).toLocaleDateString()}
                    </span>
                  </Space>
                  {canDelete && (
                    <Popconfirm
                      title="Delete evaluation"
                      description="Are you sure?"
                      onConfirm={() => deleteMutation.mutate(ev.id)}
                      okText="Yes"
                      cancelText="No"
                    >
                      <Button
                        size="small"
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        loading={
                          deleteMutation.isPending && deleteMutation.variables === ev.id
                        }
                      />
                    </Popconfirm>
                  )}
                </div>
                {ev.feedback && (
                  <p style={{ margin: 0, color: '#ededf5', whiteSpace: 'pre-wrap' }}>
                    {ev.feedback}
                  </p>
                )}
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        title="Add Evaluation"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        okText="Submit"
        confirmLoading={createMutation.isPending}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{ stage: 'reviewing' as EvaluationStage }}
        >
          <Form.Item
            name="job_id"
            label="Job"
            rules={[{ required: true, message: 'Pick a job for this evaluation' }]}
          >
            <Select
              placeholder="Select job"
              showSearch
              optionFilterProp="label"
              options={jobs.map((j) => ({ value: j.id, label: j.title }))}
              loading={jobs.length === 0}
            />
          </Form.Item>

          <Form.Item
            name="stage"
            label="Stage"
            rules={[{ required: true }]}
          >
            <Select
              options={EVALUATION_STAGES.map((s) => ({
                value: s,
                label: STAGE_LABELS[s],
              }))}
            />
          </Form.Item>

          <Form.Item name="overall_rating" label="Overall rating">
            <Rate />
          </Form.Item>

          <Form.Item name="feedback" label="Feedback">
            <Input.TextArea rows={4} placeholder="Detailed feedback (optional)" />
          </Form.Item>

          <Collapse
            ghost
            items={[
              {
                key: 'scores',
                label: 'Category scores (optional, 1-5)',
                children: (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <Form.Item name="technical_score" label="Technical">
                      <InputNumber min={1} max={5} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="communication_score" label="Communication">
                      <InputNumber min={1} max={5} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="leadership_score" label="Leadership">
                      <InputNumber min={1} max={5} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="cultural_fit_score" label="Cultural fit">
                      <InputNumber min={1} max={5} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="english_score" label="English">
                      <InputNumber min={1} max={5} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="domain_score" label="Domain">
                      <InputNumber min={1} max={5} style={{ width: '100%' }} />
                    </Form.Item>
                  </div>
                ),
              },
            ]}
          />
        </Form>
      </Modal>
    </Card>
  );
}
