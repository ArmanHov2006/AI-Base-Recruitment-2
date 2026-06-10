import axios from 'axios';
import { message } from 'antd';

let _accessToken: string | null = null;
let _isRefreshing = false;
let _pendingQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

export function setAccessToken(token: string | null): void {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export async function refreshAccessToken(): Promise<string> {
  if (_isRefreshing) {
    return new Promise((resolve, reject) => {
      _pendingQueue.push({ resolve, reject });
    });
  }
  _isRefreshing = true;
  try {
    const res = await axios.post(
      `${import.meta.env.VITE_API_BASE || 'http://localhost:8000'}/auth/refresh`,
      {},
      { withCredentials: true },
    );
    const newToken: string = res.data.access_token;
    setAccessToken(newToken);
    _pendingQueue.forEach((p) => p.resolve(newToken));
    _pendingQueue = [];
    return newToken;
  } catch (err) {
    _pendingQueue.forEach((p) => p.reject(err));
    _pendingQueue = [];
    setAccessToken(null);
    throw err;
  } finally {
    _isRefreshing = false;
  }
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // send httpOnly refresh_token cookie
});

apiClient.interceptors.request.use((config) => {
  if (_accessToken) {
    config.headers.Authorization = `Bearer ${_accessToken}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    if (error.response?.status === 401 && !original._retry) {
      // Don't attempt refresh for auth endpoints that don't require a session
      const skipPaths = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/reset-password', '/auth/verify-email', '/auth/forgot-password'];
      if (skipPaths.some((p) => original.url?.includes(p))) {
        return Promise.reject(error);
      }

      original._retry = true;

      try {
        const newToken = await refreshAccessToken();
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      } catch {
        window.location.href = '/login';
        return Promise.reject(error);
      }
    }

    if (error.response?.status !== 401) {
      const errorMessage = error.response?.data?.detail || error.message || 'An error occurred';
      message.error(errorMessage);
    }
    return Promise.reject(error);
  },
);

export default apiClient;
