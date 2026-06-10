import apiClient from './client';
import type { AuditLogEntry, BusinessEventEntry, AuditLogParams, BusinessEventParams } from '../types';

export interface PaginatedResult<T> {
  items: T[];
  total: number;
}

function parseTotalCount(header: string | undefined): number {
  const n = parseInt(header ?? '0', 10);
  return Number.isFinite(n) ? n : 0;
}

export async function listAuditLogs(params: AuditLogParams): Promise<PaginatedResult<AuditLogEntry>> {
  const response = await apiClient.get<AuditLogEntry[]>('/audit', { params });
  return {
    items: response.data,
    total: parseTotalCount(response.headers['x-total-count']),
  };
}

export async function listBusinessEvents(
  params: BusinessEventParams,
): Promise<PaginatedResult<BusinessEventEntry>> {
  const response = await apiClient.get<BusinessEventEntry[]>('/audit/events', { params });
  return {
    items: response.data,
    total: parseTotalCount(response.headers['x-total-count']),
  };
}
