import { useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import { ArrowRightOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { resendVerification } from '../api/auth';
import AuthLayout from '../components/AuthLayout';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const rawNext = searchParams.get('next') || '/';
  const next = rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null);
  const [resentEmail, setResentEmail] = useState(false);

  const onFinish = async (values: { email: string; password: string }) => {
    setLoading(true);
    setError(null);
    setUnverifiedEmail(null);
    try {
      await login(values.email, values.password);
      navigate(next, { replace: true });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      const httpStatus = (err as { response?: { status?: number } })?.response?.status;
      if (httpStatus === 403 && detail?.includes('verify your email')) {
        setUnverifiedEmail(values.email);
      } else {
        setError(detail || 'Login failed');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (!unverifiedEmail) return;
    try {
      await resendVerification(unverifiedEmail);
      setResentEmail(true);
    } catch {
      // silently ignore
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Access the Ardshinbank AI recruitment workspace."
      formLabel="Sign in"
    >
      {error && (
        <div className="auth-error" role="alert">
          {error}
        </div>
      )}

      {unverifiedEmail && (
        <Alert
          type="warning"
          style={{ marginBottom: 16 }}
          message="Email not verified"
          description={
            resentEmail ? (
              'Verification email sent. Check your inbox.'
            ) : (
              <>
                Check your inbox and click the verification link.{' '}
                <button
                  type="button"
                  onClick={handleResend}
                  style={{ background: 'none', border: 'none', padding: 0, color: 'var(--color-primary)', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  Resend email
                </button>
              </>
            )
          }
          showIcon
        />
      )}

      <Form layout="vertical" onFinish={onFinish} autoComplete="off" requiredMark={false}>
        <Form.Item
          name="email"
          label="Email"
          rules={[{ required: true, type: 'email', message: 'Valid email required' }]}
        >
          <Input
            prefix={<MailOutlined />}
            placeholder="you@ardshinbank.am"
            autoComplete="email"
          />
        </Form.Item>
        <Form.Item
          name="password"
          label="Password"
          rules={[{ required: true, message: 'Password required' }]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="Password"
            autoComplete="current-password"
          />
        </Form.Item>
        <Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            block
            icon={<ArrowRightOutlined />}
          >
            Sign in
          </Button>
        </Form.Item>
      </Form>
      <div className="auth-footer-link">
        <Link to="/forgot-password">Forgot password?</Link>
      </div>
    </AuthLayout>
  );
}
