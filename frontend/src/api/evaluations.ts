import apiClient from './client';
import type { CreateEvaluationRequest, EvaluationResponse } from '../types';

export async function listEvaluations(candidateId: string): Promise<EvaluationResponse[]> {
  const response = await apiClient.get<EvaluationResponse[]>(
    `/candidates/${candidateId}/evaluations`,
  );
  return response.data;
}

export async function createEvaluation(
  candidateId: string,
  body: CreateEvaluationRequest,
): Promise<EvaluationResponse> {
  const response = await apiClient.post<EvaluationResponse>(
    `/candidates/${candidateId}/evaluations`,
    body,
  );
  return response.data;
}

export async function updateEvaluation(
  candidateId: string,
  evalId: string,
  body: Partial<Omit<CreateEvaluationRequest, 'job_id'>>,
): Promise<EvaluationResponse> {
  const response = await apiClient.patch<EvaluationResponse>(
    `/candidates/${candidateId}/evaluations/${evalId}`,
    body,
  );
  return response.data;
}

export async function deleteEvaluation(candidateId: string, evalId: string): Promise<void> {
  await apiClient.delete(`/candidates/${candidateId}/evaluations/${evalId}`);
}
