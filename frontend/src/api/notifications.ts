import apiClient from './client';
import type { Notification, NotificationListResponse } from '../types';

export async function getNotifications(params?: {
  limit?: number;
  unread?: boolean;
}): Promise<NotificationListResponse> {
  const response = await apiClient.get<NotificationListResponse>('/notifications', { params });
  return response.data;
}

export async function markRead(id: string): Promise<Notification> {
  const response = await apiClient.patch<Notification>(`/notifications/${id}/read`);
  return response.data;
}

export async function markAllRead(): Promise<void> {
  await apiClient.post('/notifications/read-all');
}
