import apiClient from './client';

async function downloadPdf(url: string, filename: string): Promise<void> {
  const response = await apiClient.get(url, { responseType: 'blob' });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(objectUrl);
}

export function downloadCandidatePdf(candidateId: string): Promise<void> {
  return downloadPdf(`/candidates/${candidateId}/export.pdf`, `candidate-${candidateId}.pdf`);
}

export function downloadAnalyticsPdf(): Promise<void> {
  return downloadPdf('/analytics/export.pdf', 'analytics-summary.pdf');
}

export function downloadQualifiedCandidatesPdf(jobId: string, threshold: number): Promise<void> {
  return downloadPdf(
    `/jobs/${jobId}/qualified-candidates.pdf?threshold=${threshold}`,
    `qualified-candidates.pdf`,
  );
}
