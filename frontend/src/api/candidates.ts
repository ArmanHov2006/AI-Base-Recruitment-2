import apiClient from './client';
import type {
  CandidateApplicationSummary,
  CandidateListResponse,
  CandidateResponse,
  CandidateSearchFilters,
  CreateCandidateRequest,
} from '../types';

export async function listCandidates(): Promise<CandidateResponse[]> {
  const response = await apiClient.get<CandidateResponse[]>('/candidates');
  return response.data;
}

export async function getCandidate(id: string): Promise<CandidateResponse> {
  const response = await apiClient.get<CandidateResponse>(`/candidates/${id}`);
  return response.data;
}

export async function createCandidate(data: CreateCandidateRequest): Promise<CandidateResponse> {
  const response = await apiClient.post<CandidateResponse>('/candidates', data);
  return response.data;
}

export async function deleteCandidate(id: string): Promise<void> {
  await apiClient.delete(`/candidates/${id}`);
}

export async function getCandidateApplications(id: string): Promise<CandidateApplicationSummary[]> {
  const response = await apiClient.get<CandidateApplicationSummary[]>(`/candidates/${id}/applications`);
  return response.data;
}

function buildSearchParams(filters: CandidateSearchFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  if (filters.skills && filters.skills.length > 0) {
    for (const skill of filters.skills) params.append('skills', skill);
  }
  if (filters.seniority) params.set('seniority', filters.seniority);
  if (filters.status) params.set('status', filters.status);
  if (filters.location) params.set('location', filters.location);
  if (filters.years_min !== undefined) params.set('years_min', String(filters.years_min));
  if (filters.years_max !== undefined) params.set('years_max', String(filters.years_max));
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.size !== undefined) params.set('size', String(filters.size));
  return params;
}

export async function searchCandidates(
  filters: CandidateSearchFilters,
): Promise<CandidateListResponse> {
  const params = buildSearchParams(filters);
  const response = await apiClient.get<CandidateListResponse>(`/candidates/search?${params}`);
  return response.data;
}

export async function semanticSearchCandidates(
  q: string,
  limit = 20,
): Promise<CandidateListResponse> {
  const response = await apiClient.get<CandidateListResponse>('/candidates/semantic-search', {
    params: { q, limit },
  });
  return response.data;
}

export async function exportCandidatesXlsx(
  filters: Omit<CandidateSearchFilters, 'page' | 'size'>,
): Promise<void> {
  const params = buildSearchParams(filters);
  const response = await apiClient.get(`/candidates/export.xlsx?${params}`, {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'candidates.xlsx';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export async function exportCandidatesCsv(
  filters: Omit<CandidateSearchFilters, 'page' | 'size'>,
): Promise<void> {
  const params = buildSearchParams(filters);
  const response = await apiClient.get(`/candidates/export.csv?${params}`, {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'candidates.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
