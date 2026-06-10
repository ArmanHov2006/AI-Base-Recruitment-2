import axios from 'axios';
import type { TokenResponse, UserResponse } from '../types';
import apiClient, { setAccessToken } from './client';

const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export async function register(data: {
  email: string;
  password: string;
  full_name?: string;
  invite_token?: string;
}): Promise<UserResponse> {
  const response = await apiClient.post<UserResponse>('/auth/register', data);
  return response.data;
}

export async function login(data: {
  email: string;
  password: string;
}): Promise<TokenResponse> {
  // withCredentials handled by apiClient global config
  const response = await apiClient.post<TokenResponse>('/auth/login', data);
  return response.data;
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout').catch(() => {});
  setAccessToken(null);
}

export async function refresh(): Promise<string> {
  const response = await axios.post<TokenResponse>(
    `${BASE}/auth/refresh`,
    {},
    { withCredentials: true },
  );
  return response.data.access_token;
}

export async function verifyEmail(token: string): Promise<void> {
  await apiClient.post('/auth/verify-email', { token });
}

export async function resendVerification(email: string): Promise<void> {
  await apiClient.post('/auth/resend-verification', { email });
}

export async function forgotPassword(email: string): Promise<void> {
  await apiClient.post('/auth/forgot-password', { email });
}

export async function resetPassword(token: string, new_password: string): Promise<void> {
  await apiClient.post('/auth/reset-password', { token, new_password });
}

export async function getMe(): Promise<UserResponse> {
  const response = await apiClient.get<UserResponse>('/auth/me');
  return response.data;
}

export async function changePassword(data: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  await apiClient.patch('/auth/me/password', data);
}

export async function getInvitePreview(token: string): Promise<{ email: string; role: string }> {
  const response = await apiClient.get<{ email: string; role: string }>('/auth/invite-preview', {
    params: { token },
  });
  return response.data;
}
