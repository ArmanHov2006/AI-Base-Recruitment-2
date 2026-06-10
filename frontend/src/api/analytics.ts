import apiClient from './client';
import type { AnalyticsOverview, CandidateSourcesResponse, FunnelResponse, TimeToHireResponse } from '../types';

export async function getAnalyticsOverview(): Promise<AnalyticsOverview> {
  const response = await apiClient.get<AnalyticsOverview>('/analytics/overview');
  return response.data;
}

export async function getAnalyticsFunnel(jobId?: string): Promise<FunnelResponse> {
  const response = await apiClient.get<FunnelResponse>('/analytics/funnel', {
    params: jobId ? { job_id: jobId } : undefined,
  });
  return response.data;
}

export async function getTimeToHire(jobId?: string): Promise<TimeToHireResponse> {
  const response = await apiClient.get<TimeToHireResponse>('/analytics/time-to-hire', {
    params: jobId ? { job_id: jobId } : undefined,
  });
  return response.data;
}

export async function getCandidateSources(): Promise<CandidateSourcesResponse> {
  const response = await apiClient.get<CandidateSourcesResponse>('/analytics/sources');
  return response.data;
}
