import { useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import { Link, useSearchParams } from 'react-router-dom';
import { resetPassword } from '../api/auth';
import AuthLayout from '../components/AuthLayout';

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFinish = async (values: { new_password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await resetPassword(token, values.new_password);
      setDone(true);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || 'Reset failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="New password"
      subtitle="Choose a strong password for your account."
      formLabel="New password"
    >
      {done ? (
        <>
          <Alert type="success" message="Password updated. You can now sign in." showIcon />
          <div className="auth-footer-link" style={{ marginTop: 16 }}>
            <Link to="/login">Sign in</Link>
          </div>
        </>
      ) : (
        <>
          {!token && (
            <Alert type="error" message="Invalid reset link, no token found." showIcon style={{ marginBottom: 16 }} />
          )}
          {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
          <Form layout="vertical" onFinish={onFinish}>
            <Form.Item
              name="new_password"
              label="New password"
              rules={[
                { required: true },
                { min: 8 },
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
              dependencies={['new_password']}
              rules={[
                { required: true },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('new_password') === value) return Promise.resolve();
                    return Promise.reject('Passwords do not match');
                  },
                }),
              ]}
            >
              <Input.Password />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} disabled={!token} block>
              Set new password
            </Button>
          </Form>
        </>
      )}
    </AuthLayout>
  );
}
