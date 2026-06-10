import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../context/AuthContext';

export default function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (!isLoading) {
      setTimedOut(false);
      return;
    }
    const timeout = window.setTimeout(() => setTimedOut(true), 4500);
    return () => window.clearTimeout(timeout);
  }, [isLoading]);

  const loginWithNext = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;

  if (isLoading) {
    if (timedOut) {
      return <Navigate to={loginWithNext} replace />;
    }

    return (
      <div className="route-loading" role="status" aria-live="polite">
        <Spin size="large" />
        <span>Checking session...</span>
      </div>
    );
  }

  if (!user) {
    return <Navigate to={loginWithNext} replace />;
  }

  return <>{children}</>;
}
