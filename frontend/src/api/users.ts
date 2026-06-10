import apiClient from './client';
import type { UserAdminResponse, UpdateRoleRequest, UpdateActiveRequest, UserRole, InviteResponse } from '../types';

export async function listUsers(): Promise<UserAdminResponse[]> {
  const response = await apiClient.get<UserAdminResponse[]>('/users');
  return response.data;
}

export async function updateUserRole(userId: string, role: UserRole): Promise<UserAdminResponse> {
  const body: UpdateRoleRequest = { role };
  const response = await apiClient.patch<UserAdminResponse>(`/users/${userId}/role`, body);
  return response.data;
}

export async function updateUserActive(
  userId: string,
  isActive: boolean,
): Promise<UserAdminResponse> {
  const body: UpdateActiveRequest = { is_active: isActive };
  const response = await apiClient.patch<UserAdminResponse>(`/users/${userId}/active`, body);
  return response.data;
}

export async function createInvite(email: string, role: UserRole): Promise<InviteResponse> {
  const response = await apiClient.post<InviteResponse>('/users/invites', { email, role });
  return response.data;
}

export async function listInvites(): Promise<InviteResponse[]> {
  const response = await apiClient.get<InviteResponse[]>('/users/invites');
  return response.data;
}

export async function revokeInvite(inviteId: string): Promise<void> {
  await apiClient.delete(`/users/invites/${inviteId}`);
}
