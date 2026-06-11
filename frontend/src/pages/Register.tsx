import { useEffect, useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import { Link, useSearchParams } from 'react-router-dom';
import { getInvitePreview, register } from '../api/auth';
import AuthLayout from '../components/AuthLayout';

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  recruiter: 'Recruiter',
  hr_manager: 'HR Manager',
  viewer: 'Viewer',
};

export default function Register() {
  const [searchParams] = useSearchParams();
  const inviteToken = searchParams.get('invite');
  const [inviteEmail, setInviteEmail] = useState<string | null>(null);
  const [inviteRole, setInviteRole] = useState<string | null>(null);

  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!inviteToken) return;
    getInvitePreview(inviteToken)
      .then((data) => {
        setInviteEmail(data.email);
        setInviteRole(data.role);
        form.setFieldsValue({ email: data.email });
      })
      .catch(() => {
        // Invalid/expired invite — let the server surface the error on submit
      });
  }, [inviteToken, form]);

  const onFinish = async (values: {
    email: string;
    password: string;
    confirm: string;
    full_name?: string;
  }) => {
    setLoading(true);
    setError(null);
    try {
      await register({
        email: values.email,
        password: values.password,
        full_name: values.full_name,
        invite_token: inviteToken ?? undefined,
      });
      setDone(true);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Create account"
      subtitle="Set up your AI_Based_recruitment recruitment workspace access."
      formLabel="Create account"
    >
      {inviteToken && (
          <Alert
            type="info"
            style={{ marginBottom: 16 }}
            message={
              inviteRole
                ? `You've been invited as ${ROLE_LABELS[inviteRole] ?? inviteRole}`
                : "You've been invited"
            }
            description="Complete registration below to activate your account."
            showIcon
          />
        )}

        {done ? (
          <Alert
            type="success"
            message={inviteToken ? 'Account created' : 'Check your email'}
            description={
              inviteToken
                ? 'Your account is ready. You can sign in now.'
                : 'We sent a verification link. Click it to activate your account.'
            }
            showIcon
          />
        ) : (
          <>
            {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
            <Form form={form} layout="vertical" onFinish={onFinish}>
              <Form.Item name="full_name" label="Full name">
                <Input placeholder="Arman Hovhannisyan" />
              </Form.Item>
              <Form.Item
                name="email"
                label="Email"
                rules={[{ required: true, type: 'email', message: 'Valid email required' }]}
              >
                <Input
                  placeholder="you@airecruitment.com"
                  disabled={!!inviteEmail}
                />
              </Form.Item>
              <Form.Item
                name="password"
                label="Password"
                rules={[
                  { required: true },
                  { min: 8, message: 'At least 8 characters' },
                  {
                    pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
                    message: 'Must have uppercase, lowercase, and a digit',
                  },
                ]}
              >
                <Input.Password />
              </Form.Item>
              <Form.Item
                name="confirm"
                label="Confirm password"
                dependencies={['password']}
                rules={[
                  { required: true },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('password') === value) return Promise.resolve();
                      return Promise.reject('Passwords do not match');
                    },
                  }),
                ]}
              >
                <Input.Password />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                Register
              </Button>
            </Form>
          </>
        )}

        <div className="auth-footer-link" style={{ marginTop: 16 }}>
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
    </AuthLayout>
  );
}
