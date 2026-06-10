import {
  Card,
  Tag,
  Button,
  Skeleton,
  Timeline,
  Popconfirm,
  Avatar,
  message,
  Modal,
  DatePicker,
  Input,
} from 'antd';
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  MailOutlined,
  PhoneOutlined,
  EnvironmentOutlined,
  CalendarOutlined,
  EditOutlined,
  UserOutlined,
  FilePdfOutlined,
  LinkedinOutlined,
  GithubOutlined,
  DollarOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { getCandidate, deleteCandidate, getCandidateApplications } from '../api/candidates';
import { setInterview } from '../api/applications';
import { downloadCandidatePdf } from '../api/pdf';
import { downloadGdprExport } from '../api/gdpr';
import { useAuth } from '../context/AuthContext';
import type { CandidateApplicationSummary } from '../types';
import EvaluationsSection from '../components/Evaluations/EvaluationsSection';
import NotesSection from '../components/Notes/NotesSection';
import AiChatPanel from '../components/AiChat/AiChatPanel';

const seniorityColorMap: Record<string, string> = {
  junior: 'green',
  mid: 'blue',
  senior: 'orange',
  lead: 'purple',
};

const statusColorMap: Record<string, string> = {
  active: 'green',
  archived: 'default',
  hired: 'blue',
};

export default function CandidateDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isReadOnly = user?.role === 'viewer';
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleExportPdf = async () => {
    if (!id) return;
    setExportingPdf(true);
    try {
      await downloadCandidatePdf(id);
    } catch {
      message.error('PDF export failed');
    } finally {
      setExportingPdf(false);
    }
  };

  const handleGdprExport = async () => {
    if (!id) return;
    setExporting(true);
    try {
      await downloadGdprExport(id);
      message.success('GDPR export downloaded');
    } catch {
      message.error('GDPR export failed');
    } finally {
      setExporting(false);
    }
  };

  const [editingInterview, setEditingInterview] = useState<CandidateApplicationSummary | null>(null);
  const [interviewAt, setInterviewAt] = useState<dayjs.Dayjs | null>(null);
  const [interviewLocation, setInterviewLocation] = useState('');

  const { data: candidate, isLoading } = useQuery({
    queryKey: ['candidate', id],
    queryFn: () => getCandidate(id!),
    enabled: !!id,
  });

  const { data: candidateApplications = [] } = useQuery({
    queryKey: ['candidate-applications', id],
    queryFn: () => getCandidateApplications(id!),
    enabled: !!id,
  });

  const interviewApplications = candidateApplications.filter((a) => a.status === 'interview');

  const interviewMutation = useMutation({
    mutationFn: ({ app, scheduledAt, location }: { app: CandidateApplicationSummary; scheduledAt: string | null; location: string | null }) =>
      setInterview(app.job_id, app.id, scheduledAt, location),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidate-applications', id] });
      message.success('Interview updated');
      setEditingInterview(null);
    },
    onError: () => {
      message.error('Could not update interview');
    },
  });

  const openInterviewEdit = (app: CandidateApplicationSummary) => {
    setEditingInterview(app);
    setInterviewAt(app.interview_scheduled_at ? dayjs(app.interview_scheduled_at) : null);
    setInterviewLocation(app.interview_location ?? '');
  };

  const submitInterviewEdit = () => {
    if (!editingInterview) return;
    interviewMutation.mutate({
      app: editingInterview,
      scheduledAt: interviewAt ? interviewAt.toISOString() : null,
      location: interviewLocation.trim() || null,
    });
  };

  const deleteMutation = useMutation({
    mutationFn: deleteCandidate,
    onSuccess: () => {
      message.success('Candidate deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      navigate('/');
    },
  });

  const handleDelete = () => {
    if (id) {
      deleteMutation.mutate(id);
    }
  };

  const getInitials = (name?: string) => {
    if (!name) return '?';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  if (isLoading) {
    return (
      <div>
        <div style={{ marginBottom: 24 }}>
          <Skeleton.Button active size="small" style={{ width: 100 }} />
        </div>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ flex: '0 0 300px' }}>
            <Card>
              <Skeleton avatar active paragraph={{ rows: 4 }} />
            </Card>
          </div>
          <div style={{ flex: 1, minWidth: 300 }}>
            <Card style={{ marginBottom: 16 }}>
              <Skeleton active paragraph={{ rows: 3 }} />
            </Card>
            <Card style={{ marginBottom: 16 }}>
              <Skeleton active paragraph={{ rows: 2 }} />
            </Card>
          </div>
        </div>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <p>Candidate not found</p>
        <Button onClick={() => (window.history.state?.idx ?? 0) > 0 ? navigate(-1) : navigate('/candidates')}>Back</Button>
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <Button icon={<ArrowLeftOutlined />} onClick={() => (window.history.state?.idx ?? 0) > 0 ? navigate(-1) : navigate('/candidates')}>
          Back
        </Button>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            icon={<FilePdfOutlined />}
            loading={exportingPdf}
            onClick={handleExportPdf}
          >
            Export PDF
          </Button>
          {isAdmin && (
            <Button
              icon={<SafetyCertificateOutlined />}
              loading={exporting}
              onClick={handleGdprExport}
            >
              GDPR Export
            </Button>
          )}
          <Popconfirm
            title="Delete candidate"
            description="Are you sure you want to delete this candidate?"
            onConfirm={handleDelete}
            okText="Yes"
            cancelText="No"
          >
            <Button danger icon={<DeleteOutlined />} loading={deleteMutation.isPending}>
              Delete
            </Button>
          </Popconfirm>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div style={{ flex: '0 0 300px' }}>
          <Card>
            <div style={{ textAlign: 'center', marginBottom: 24 }}>
              <Avatar
                size={80}
                style={{
                  backgroundColor: '#1677ff',
                  fontSize: 28,
                  marginBottom: 16,
                }}
                icon={!candidate.name && <UserOutlined />}
              >
                {candidate.name && getInitials(candidate.name)}
              </Avatar>
              <h2 style={{ margin: '0 0 8px 0', fontSize: 20 }}>
                {candidate.name || 'Unknown'}
              </h2>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                {candidate.seniority && (
                  <Tag color={seniorityColorMap[candidate.seniority] || 'default'}>
                    {candidate.seniority.charAt(0).toUpperCase() + candidate.seniority.slice(1)}
                  </Tag>
                )}
                {candidate.status && (
                  <Tag color={statusColorMap[candidate.status] || 'default'}>
                    {candidate.status.charAt(0).toUpperCase() + candidate.status.slice(1)}
                  </Tag>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {candidate.email && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <MailOutlined style={{ color: '#999' }} />
                  <span>{candidate.email}</span>
                </div>
              )}
              {candidate.phone && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <PhoneOutlined style={{ color: '#999' }} />
                  <span>{candidate.phone}</span>
                </div>
              )}
              {candidate.location && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <EnvironmentOutlined style={{ color: '#999' }} />
                  <span>{candidate.location}</span>
                </div>
              )}
              {candidate.linkedin_url && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <LinkedinOutlined style={{ color: '#999' }} />
                  <a href={candidate.linkedin_url} target="_blank" rel="noopener noreferrer">
                    LinkedIn
                  </a>
                </div>
              )}
              {candidate.github_url && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <GithubOutlined style={{ color: '#999' }} />
                  <a href={candidate.github_url} target="_blank" rel="noopener noreferrer">
                    GitHub
                  </a>
                </div>
              )}
              {candidate.desired_salary != null && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <DollarOutlined style={{ color: '#999' }} />
                  <span>{candidate.desired_salary.toLocaleString()}</span>
                </div>
              )}
              {candidate.created_at && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CalendarOutlined style={{ color: '#999' }} />
                  <span>Added {new Date(candidate.created_at).toLocaleDateString()}</span>
                </div>
              )}
            </div>
          </Card>
        </div>

        <div style={{ flex: 1, minWidth: 300 }}>
          {interviewApplications.length > 0 && (
            <Card
              style={{ marginBottom: 16, borderColor: 'var(--color-primary, #5b6af5)', borderWidth: 1.5 }}
              styles={{ header: { borderBottomColor: 'var(--color-primary, #5b6af5)' } }}
              title={
                <span style={{ color: 'var(--color-primary, #5b6af5)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CalendarOutlined />
                  Interview
                </span>
              }
            >
              {interviewApplications.map((app) => (
                <div key={app.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{app.job_title || 'Unknown position'}</span>
                    {app.interview_scheduled_at ? (
                      <>
                        <span style={{ fontSize: 13 }}>
                          {new Date(app.interview_scheduled_at).toLocaleString(undefined, {
                            weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                          })}
                        </span>
                        {app.interview_location && (
                          <span style={{ fontSize: 12, color: 'var(--color-muted)' }}>
                            <EnvironmentOutlined style={{ marginRight: 4 }} />
                            {app.interview_location}
                          </span>
                        )}
                      </>
                    ) : (
                      <span style={{ fontSize: 12, color: 'var(--color-muted)' }}>No time scheduled yet</span>
                    )}
                  </div>
                  {!isReadOnly && (
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => openInterviewEdit(app)}
                    >
                      {app.interview_scheduled_at ? 'Edit' : 'Schedule'}
                    </Button>
                  )}
                </div>
              ))}
            </Card>
          )}

          {id && <AiChatPanel candidateId={id} />}

          {candidate.summary && (
            <Card title="Summary" style={{ marginBottom: 16 }}>
              <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{candidate.summary}</p>
            </Card>
          )}

          <Card title="Skills" style={{ marginBottom: 16 }}>
            {candidate.skills && candidate.skills.length > 0 ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {candidate.skills.map((skill) => (
                  <Tag key={skill} color="blue">
                    {skill}
                  </Tag>
                ))}
              </div>
            ) : (
              <p style={{ margin: 0, color: '#999' }}>No skills listed</p>
            )}
          </Card>

          <Card
            title={`Experience${candidate.years_experience !== undefined ? ` (${candidate.years_experience} years)` : ''}`}
            style={{ marginBottom: 16 }}
          >
            {candidate.work_experiences && candidate.work_experiences.length > 0 ? (
              <Timeline
                items={candidate.work_experiences.map((exp) => ({
                  children: (
                    <div>
                      <div style={{ fontWeight: 600 }}>
                        {exp.role || 'Unknown role'}
                        {exp.company ? ` · ${exp.company}` : ''}
                      </div>
                      <div style={{ color: '#999', fontSize: 12, marginBottom: 6 }}>
                        {(exp.start_date || '?') + ' – ' + (exp.end_date || 'present')}
                      </div>
                      {exp.description && (
                        <p style={{ margin: '0 0 6px 0', color: '#555', whiteSpace: 'pre-wrap' }}>
                          {exp.description}
                        </p>
                      )}
                      {exp.achievements && exp.achievements.length > 0 && (
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {exp.achievements.map((bullet, i) => (
                            <li key={i} style={{ color: '#444' }}>{bullet}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ),
                }))}
              />
            ) : (
              <p style={{ margin: 0, color: '#999' }}>No work experience listed</p>
            )}
          </Card>

          <Card title="Education" style={{ marginBottom: 16 }}>
            {candidate.education && candidate.education.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {candidate.education.map((edu, index) => (
                  <Card key={index} size="small" type="inner">
                    <div style={{ fontWeight: 600 }}>{edu.institution}</div>
                    {edu.degree && <div style={{ color: '#666' }}>{edu.degree}</div>}
                    {edu.year && <div style={{ color: '#999', fontSize: 12 }}>{edu.year}</div>}
                  </Card>
                ))}
              </div>
            ) : (
              <p style={{ margin: 0, color: '#999' }}>No education listed</p>
            )}
          </Card>

          {candidate.certifications && candidate.certifications.length > 0 && (
            <Card title="Certifications" style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {candidate.certifications.map((cert) => (
                  <Tag key={cert} color="gold">
                    {cert}
                  </Tag>
                ))}
              </div>
            </Card>
          )}

          {candidate.languages && candidate.languages.length > 0 && (
            <Card title="Languages" style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {candidate.languages.map((lang) => (
                  <Tag key={lang} color="cyan">
                    {lang}
                  </Tag>
                ))}
              </div>
            </Card>
          )}

          {id && <EvaluationsSection candidateId={id} />}
          {id && <NotesSection candidateId={id} />}
        </div>
      </div>

      <Modal
        title="Interview Details"
        open={!!editingInterview}
        onCancel={() => setEditingInterview(null)}
        onOk={submitInterviewEdit}
        okText="Save"
        confirmLoading={interviewMutation.isPending}
        destroyOnHidden
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
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
          {editingInterview?.interview_scheduled_at && (
            <Button
              danger
              size="small"
              type="text"
              onClick={() => interviewMutation.mutate({ app: editingInterview, scheduledAt: null, location: null })}
            >
              Clear interview
            </Button>
          )}
        </div>
      </Modal>
    </div>
  );
}
