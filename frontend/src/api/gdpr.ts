import apiClient from './client';

/**
 * Admin-only. Downloads the candidate's full GDPR data bundle as a JSON file.
 */
export async function downloadGdprExport(candidateId: string): Promise<void> {
  const response = await apiClient.get(`/candidates/${candidateId}/gdpr-export`, {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], { type: 'application/json' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `gdpr-export-${candidateId}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
