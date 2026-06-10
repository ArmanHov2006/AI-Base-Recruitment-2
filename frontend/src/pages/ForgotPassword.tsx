import { useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import { Link } from 'react-router-dom';
import { forgotPassword } from '../api/auth';
import AuthLayout from '../components/AuthLayout';

export default function ForgotPassword() {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const onFinish = async (values: { email: string }) => {
    setLoading(true);
    try {
      await forgotPassword(values.email);
    } finally {
      setLoading(false);
      setDone(true); // always show success — no user enumeration
    }
  };

  return (
    <AuthLayout
      title="Reset password"
      subtitle="Enter your email and we'll send a reset link."
      formLabel="Reset password"
    >
      {done ? (
        <Alert
          type="info"
          message="Check your email"
          description="If an account exists for that address, we sent a reset link."
          showIcon
        />
      ) : (
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="email"
            label="Email"
            rules={[{ required: true, type: 'email' }]}
          >
            <Input placeholder="you@ardshinbank.am" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            Send reset link
          </Button>
        </Form>
      )}

      <div className="auth-footer-link" style={{ marginTop: 16 }}>
        <Link to="/login">Back to sign in</Link>
      </div>
    </AuthLayout>
  );
}
