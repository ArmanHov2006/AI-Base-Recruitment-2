import { getAccessToken } from './client';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export interface ChatStreamParams {
  candidateId: string;
  message: string;
  jobId?: string;
  signal?: AbortSignal;
  onToken: (chunk: string) => void;
}

/**
 * POST /ai/chat and stream the plain-text answer token-by-token.
 * Uses native fetch (not axios) so the ReadableStream body is accessible.
 */
export async function streamChat({
  candidateId,
  message,
  jobId,
  signal,
  onToken,
}: ChatStreamParams): Promise<void> {
  const token = getAccessToken();
  const res = await fetch(`${API_BASE}/ai/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: 'include',
    body: JSON.stringify({
      candidate_id: candidateId,
      message,
      job_id: jobId ?? null,
    }),
    signal,
  });

  if (!res.ok || !res.body) {
    let detail = `Chat request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* non-JSON error body — keep the status-based message */
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    if (chunk) onToken(chunk);
  }
}
