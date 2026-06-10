import apiClient from './client';
import type { ComparisonResponse, HeadToHeadResponse } from '../types';

export async function listComparisons(jobId: string): Promise<ComparisonResponse[]> {
  const response = await apiClient.get<ComparisonResponse[]>('/comparisons', {
    params: { job_id: jobId },
  });
  return response.data;
}

export async function createComparison(
  jobId: string,
  candidateIds: string[],
): Promise<ComparisonResponse> {
  const response = await apiClient.post<ComparisonResponse>('/comparisons', {
    job_id: jobId,
    candidate_ids: candidateIds,
  });
  return response.data;
}

export async function getComparison(id: string): Promise<ComparisonResponse> {
  const response = await apiClient.get<ComparisonResponse>(`/comparisons/${id}`);
  return response.data;
}

export async function analyzeComparison(id: string): Promise<HeadToHeadResponse> {
  const response = await apiClient.post<HeadToHeadResponse>(`/comparisons/${id}/analyze`);
  return response.data;
}
