import apiClient from './client';
import type { JobResponse, CreateJobRequest, UpdateJobRequest, LeaderboardEntry, JobAnalyticsSummary, ShortlistResponse, GenerateDescriptionRequest, GenerateDescriptionResponse } from '../types';

export async function listJobs(): Promise<JobResponse[]> {
  const response = await apiClient.get<JobResponse[]>('/jobs');
  return response.data;
}

export async function getJob(id: string): Promise<JobResponse> {
  const response = await apiClient.get<JobResponse>(`/jobs/${id}`);
  return response.data;
}

export async function createJob(data: CreateJobRequest): Promise<JobResponse> {
  const response = await apiClient.post<JobResponse>('/jobs', data);
  return response.data;
}

export async function patchJob(id: string, data: UpdateJobRequest): Promise<JobResponse> {
  const response = await apiClient.patch<JobResponse>(`/jobs/${id}`, data);
  return response.data;
}

export async function deleteJob(id: string): Promise<void> {
  await apiClient.delete(`/jobs/${id}`);
}

export async function getJobLeaderboard(jobId: string): Promise<LeaderboardEntry[]> {
  const response = await apiClient.get<LeaderboardEntry[]>(`/jobs/${jobId}/leaderboard`, {
    params: { limit: 500 },
  });
  return response.data;
}

export async function getJobAnalyticsSummary(jobId: string): Promise<JobAnalyticsSummary> {
  const response = await apiClient.get<JobAnalyticsSummary>(`/jobs/${jobId}/analytics-summary`);
  return response.data;
}

export async function getJobShortlist(
  jobId: string,
  target?: number | null,
  threshold?: number | null,
): Promise<ShortlistResponse> {
  const params: Record<string, string> = {};
  if (target != null) params.target = String(target);
  if (threshold != null) params.threshold = String(threshold);
  const response = await apiClient.get<ShortlistResponse>(`/jobs/${jobId}/shortlist`, { params });
  return response.data;
}

export async function generateJobDescription(
  data: GenerateDescriptionRequest,
): Promise<GenerateDescriptionResponse> {
  const response = await apiClient.post<GenerateDescriptionResponse>('/jobs/generate-description', data);
  return response.data;
}
