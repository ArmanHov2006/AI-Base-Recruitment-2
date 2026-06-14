/**
 * frontend/src/api/interviews.ts
 *
 * Public interview API calls — these do NOT use the JWT-interceptor axios
 * instance because the public recorder endpoints have no auth requirement.
 * Uses plain fetch to avoid sending Authorization headers.
 */

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export interface UploadUrlResponse {
  url: string;
  fields: Record<string, string>;
  file_id: string;
}

export interface StartAttemptResponse {
  session_id: string;
  question_index: number;
  attempt_consumed_at: string;
}

/**
 * Request a presigned POST policy from the backend.
 * Returns the upload URL, the required form fields, and the generated file_id.
 */
export async function getUploadUrl(contentType: string): Promise<UploadUrlResponse> {
  const res = await fetch(`${API_BASE}/interviews/public/upload-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content_type: contentType }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to get upload URL: ${res.status} ${detail}`);
  }
  return res.json() as Promise<UploadUrlResponse>;
}

/**
 * Mark the attempt for session+questionIndex as consumed.
 * Returns 409 if already consumed (caller should redirect to attempt-used screen).
 */
export async function startAnswerAttempt(
  sessionId: string,
  questionIndex: number,
): Promise<StartAttemptResponse> {
  const res = await fetch(
    `${API_BASE}/interviews/public/${sessionId}/answers/${questionIndex}/start`,
    { method: 'POST' },
  );
  if (res.status === 409) {
    throw Object.assign(new Error('attempt already used'), { status: 409 });
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to start attempt: ${res.status} ${detail}`);
  }
  return res.json() as Promise<StartAttemptResponse>;
}

/**
 * Upload a video Blob to MinIO using the presigned POST policy fields.
 * `onProgress` is called with 0–100 as the XHR upload progresses.
 */
export function uploadVideoBlob(
  uploadUrl: string,
  fields: Record<string, string>,
  fileId: string,
  blob: Blob,
  contentType: string,
  onProgress: (pct: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    // Fields must come before the file per S3 POST spec
    for (const [k, v] of Object.entries(fields)) {
      formData.append(k, v);
    }
    formData.append('key', fileId);
    formData.append('Content-Type', contentType);
    formData.append('file', blob, `${fileId}.webm`);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', uploadUrl);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      // MinIO presigned POST returns 204 No Content on success
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Upload failed with status ${xhr.status}: ${xhr.responseText}`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.send(formData);
  });
}
