import apiClient from './client';
import type { JobApplication, UserSettableStatus } from '../types';

export async function listApplications(jobId: string): Promise<JobApplication[]> {
  const response = await apiClient.get<JobApplication[]>(`/jobs/${jobId}/applications`);
  return response.data;
}

export async function getApplication(
  jobId: string,
  applicationId: string,
): Promise<JobApplication> {
  const response = await apiClient.get<JobApplication>(
    `/jobs/${jobId}/applications/${applicationId}`,
  );
  return response.data;
}

export async function createApplication(jobId: string, fileId: string): Promise<JobApplication> {
  const response = await apiClient.post<JobApplication>(`/jobs/${jobId}/applications`, {
    file_id: fileId,
  });
  return response.data;
}

export async function updateApplicationStatus(
  jobId: string,
  applicationId: string,
  status: UserSettableStatus,
): Promise<JobApplication> {
  const response = await apiClient.patch<JobApplication>(
    `/jobs/${jobId}/applications/${applicationId}`,
    { status },
  );
  return response.data;
}

export async function bulkCreateApplications(
  jobId: string,
  fileIds: string[],
): Promise<{ application_ids: string[] }> {
  const response = await apiClient.post<{ application_ids: string[] }>(
    `/jobs/${jobId}/applications/bulk`,
    { file_ids: fileIds },
  );
  return response.data;
}

export async function deleteApplication(jobId: string, applicationId: string): Promise<void> {
  await apiClient.delete(`/jobs/${jobId}/applications/${applicationId}`);
}

export async function setInterview(
  jobId: string,
  applicationId: string,
  scheduledAt: string | null,
  location: string | null,
): Promise<JobApplication> {
  const response = await apiClient.patch<JobApplication>(
    `/jobs/${jobId}/applications/${applicationId}/interview`,
    { scheduled_at: scheduledAt, location },
  );
  return response.data;
}
