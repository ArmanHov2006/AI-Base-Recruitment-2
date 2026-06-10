import apiClient from './client';
import type { CandidateData } from '../types';

export async function parseResume(file_id: string): Promise<CandidateData> {
  const response = await apiClient.post<CandidateData>('/parse', { file_id });
  return response.data;
}
