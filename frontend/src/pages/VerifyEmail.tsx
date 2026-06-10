import { useEffect, useState } from 'react';
import { Alert, Spin } from 'antd';
import { Link, useSearchParams } from 'react-router-dom';
import { verifyEmail } from '../api/auth';
import AuthLayout from '../components/AuthLayout';

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [detail, setDetail] = useState<string>('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setDetail('No verification token in URL.');
      return;
    }
    verifyEmail(token)
      .then(() => setStatus('success'))
      .catch((err: unknown) => {
        const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setDetail(msg || 'Verification failed');
        setStatus('error');
      });
  }, [token]);

  return (
    <AuthLayout title="Email verification" formLabel="Email verification">
      <div style={{ textAlign: 'center' }}>
        {status === 'loading' && <Spin size="large" />}
        {status === 'success' && (
          <>
            <Alert type="success" message="Email verified" description="Your account is now active." showIcon />
            <div className="auth-footer-link" style={{ marginTop: 16 }}>
              <Link to="/login">Sign in</Link>
            </div>
          </>
        )}
        {status === 'error' && (
          <>
            <Alert type="error" message="Verification failed" description={detail} showIcon />
            <div className="auth-footer-link" style={{ marginTop: 16 }}>
              <Link to="/login">Back to sign in</Link>
            </div>
          </>
        )}
      </div>
    </AuthLayout>
  );
}
