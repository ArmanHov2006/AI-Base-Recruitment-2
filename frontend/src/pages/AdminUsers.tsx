import { useState } from 'react';
import {
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import {
  createInvite,
  listInvites,
  listUsers,
  revokeInvite,
  updateUserActive,
  updateUserRole,
} from '../api/users';
import type { InviteResponse, UserAdminResponse, UserRole } from '../types';

const { Title } = Typography;

const ROLE_OPTIONS: { label: string; value: UserRole }[] = [
  { label: 'Admin', value: 'admin' },
  { label: 'Recruiter', value: 'recruiter' },
  { label: 'HR Manager', value: 'hr_manager' },
  { label: 'Viewer', value: 'viewer' },
];


export default function AdminUsers() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm] = Form.useForm();
  const isAdmin = currentUser?.role === 'admin';

  const { data: users = [], isLoading: usersLoading } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: listUsers,
    enabled: isAdmin,
  });

  const { data: invites = [], isLoading: invitesLoading } = useQuery({
    queryKey: ['admin', 'invites'],
    queryFn: listInvites,
    enabled: isAdmin,
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) =>
      updateUserRole(userId, role),
    onMutate: ({ userId }) => setUpdatingId(userId),
    onSuccess: () => {
      message.success('Role updated');
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: () => message.error('Failed to update role'),
    onSettled: () => setUpdatingId(null),
  });

  const activeMutation = useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      updateUserActive(userId, isActive),
    onMutate: ({ userId }) => setUpdatingId(userId),
    onSuccess: () => {
      message.success('Status updated');
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: () => message.error('Failed to update status'),
    onSettled: () => setUpdatingId(null),
  });

  const inviteMutation = useMutation({
    mutationFn: ({ email, role }: { email: string; role: UserRole }) =>
      createInvite(email, role),
    onSuccess: () => {
      message.success('Invite sent');
      queryClient.invalidateQueries({ queryKey: ['admin', 'invites'] });
      setInviteOpen(false);
      inviteForm.resetFields();
    },
    onError: () => message.error('Failed to send invite'),
  });

  const revokeMutation = useMutation({
    mutationFn: (inviteId: string) => revokeInvite(inviteId),
    onSuccess: () => {
      message.success('Invite revoked');
      queryClient.invalidateQueries({ queryKey: ['admin', 'invites'] });
    },
    onError: () => message.error('Failed to revoke invite'),
  });

  const userColumns: ColumnsType<UserAdminResponse> = [
    {
      title: 'Name',
      key: 'name',
      render: (_, r) => r.full_name || <span style={{ color: '#94a3b8' }}>—</span>,
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: 'Role',
      key: 'role',
      render: (_, r) => (
        <Select
          value={r.role}
          options={ROLE_OPTIONS}
          style={{ width: 140 }}
          disabled={r.id === currentUser?.id || updatingId === r.id}
          onChange={(role) => roleMutation.mutate({ userId: r.id, role })}
          variant="borderless"
        />
      ),
    },
    {
      title: 'Active',
      key: 'active',
      render: (_, r) => (
        <Switch
          checked={r.is_active}
          loading={updatingId === r.id}
          disabled={r.id === currentUser?.id || updatingId === r.id}
          onChange={(checked) => {
            if (r.id === currentUser?.id) return;
            activeMutation.mutate({ userId: r.id, isActive: checked });
          }}
        />
      ),
    },
    {
      title: 'Verified',
      key: 'verified',
      render: (_, r) =>
        r.is_verified ? (
          <Tag color="success">Verified</Tag>
        ) : (
          <Tag color="warning">Unverified</Tag>
        ),
    },
    {
      title: 'Joined',
      key: 'created_at',
      render: (_, r) => new Date(r.created_at).toLocaleDateString(),
    },
  ];

  const inviteColumns: ColumnsType<InviteResponse> = [
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: 'Role',
      key: 'role',
      render: (_, r) => {
        const opt = ROLE_OPTIONS.find((o) => o.value === r.role);
        return <Tag>{opt?.label ?? r.role}</Tag>;
      },
    },
    {
      title: 'Expires',
      key: 'expires_at',
      render: (_, r) => new Date(r.expires_at).toLocaleString(),
    },
    {
      title: 'Sent',
      key: 'created_at',
      render: (_, r) => new Date(r.created_at).toLocaleDateString(),
    },
    {
      title: '',
      key: 'actions',
      render: (_, r) => (
        <Popconfirm
          title="Revoke this invite?"
          onConfirm={() => revokeMutation.mutate(r.id)}
          okText="Revoke"
          okButtonProps={{ danger: true }}
        >
          <Button type="link" danger size="small">
            Revoke
          </Button>
        </Popconfirm>
      ),
    },
  ];

  if (!isAdmin) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Title level={4}>Access Denied</Title>
        <p>Admin role required to view this page.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">User Management</h1>
          <p className="page-description">Manage user roles, access, and invites.</p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setInviteOpen(true)}
        >
          Invite User
        </Button>
      </div>

      <Tabs
        items={[
          {
            key: 'users',
            label: 'Users',
            children: (
              <Table
                rowKey="id"
                columns={userColumns}
                dataSource={users}
                loading={usersLoading}
                pagination={{ pageSize: 20 }}
                rowClassName={(r) => (r.id === currentUser?.id ? 'ant-table-row-selected' : '')}
              />
            ),
          },
          {
            key: 'invites',
            label: `Pending Invites${invites.length ? ` (${invites.length})` : ''}`,
            children: (
              <Table
                rowKey="id"
                columns={inviteColumns}
                dataSource={invites}
                loading={invitesLoading}
                pagination={{ pageSize: 20 }}
                locale={{ emptyText: 'No pending invites' }}
              />
            ),
          },
        ]}
      />

      <Modal
        title="Invite User"
        open={inviteOpen}
        onCancel={() => { setInviteOpen(false); inviteForm.resetFields(); }}
        footer={null}
        destroyOnHidden
      >
        <Form
          form={inviteForm}
          layout="vertical"
          onFinish={(values: { email: string; role: UserRole }) =>
            inviteMutation.mutate(values)
          }
        >
          <Form.Item
            name="email"
            label="Email"
            rules={[{ required: true, type: 'email', message: 'Valid email required' }]}
          >
            <Input placeholder="colleague@ardshinbank.am" />
          </Form.Item>
          <Form.Item
            name="role"
            label="Role"
            initialValue="recruiter"
            rules={[{ required: true }]}
          >
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={inviteMutation.isPending}
              block
            >
              Send Invite
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
