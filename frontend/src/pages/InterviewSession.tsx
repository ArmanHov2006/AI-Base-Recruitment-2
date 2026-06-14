/**
 * frontend/src/pages/InterviewSession.tsx
 *
 * Public candidate recorder — NO app shell, NO auth required.
 * Accessible at /interview/:sessionId
 *
 * State machine (PRD §10.3):
 *   permission-prompt → permission-denied | unsupported-browser | ready-check
 *   ready-check       → recording  (calls start-attempt, consuming the single take)
 *   recording         → auto-stopped (2 min) | uploading  (Stop button)
 *   auto-stopped      → uploading
 *   uploading         → submitted | upload-failed
 *   upload-failed     → uploading  (Retry, same blob)
 *   attempt-used      (terminal — shown on mount if already consumed, or on 409)
 *   submitted         (terminal)
 *
 * Design (D5 calm theme, §10.4 a11y):
 *   - Light/calm surface, distinct from dark dashboard
 *   - Fira Sans, ≥16px question text, accent #5b6af5
 *   - Touch targets ≥44px, 375px portrait primary
 *   - prefers-reduced-motion disables rec dot pulse
 *   - aria-live for recording state + timer
 *   - contrast ≥4.5:1 on all text
 */

import { useCallback, useEffect, useReducer, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { getUploadUrl, startAnswerAttempt, uploadVideoBlob } from '../api/interviews';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type RecorderState =
  | 'permission-prompt'
  | 'permission-denied'
  | 'unsupported-browser'
  | 'ready-check'
  | 'recording'
  | 'auto-stopped'
  | 'uploading'
  | 'upload-failed'
  | 'attempt-used'
  | 'submitted';

interface State {
  phase: RecorderState;
  /** Seconds remaining while recording */
  secondsLeft: number;
  /** Upload progress 0–100 */
  uploadPct: number;
  /** Error detail for upload-failed screen */
  uploadError: string | null;
  /** Agency display_name fetched from session info */
  displayName: string | null;
  /** Question text shown during ready-check and recording */
  questionText: string;
}

type Action =
  | { type: 'SET_PHASE'; phase: RecorderState }
  | { type: 'TICK' }
  | { type: 'SET_UPLOAD_PCT'; pct: number }
  | { type: 'SET_UPLOAD_ERROR'; error: string }
  | { type: 'SET_SESSION_INFO'; displayName: string | null; questionText: string };

const MAX_SECONDS = 120;

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_PHASE':
      return { ...state, phase: action.phase };
    case 'TICK':
      return { ...state, secondsLeft: Math.max(0, state.secondsLeft - 1) };
    case 'SET_UPLOAD_PCT':
      return { ...state, uploadPct: action.pct };
    case 'SET_UPLOAD_ERROR':
      return { ...state, phase: 'upload-failed', uploadError: action.error };
    case 'SET_SESSION_INFO':
      return { ...state, displayName: action.displayName, questionText: action.questionText };
    default:
      return state;
  }
}

const initialState: State = {
  phase: 'permission-prompt',
  secondsLeft: MAX_SECONDS,
  uploadPct: 0,
  uploadError: null,
  displayName: null,
  questionText: 'Tell us about yourself and why you applied for this role.',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function isMediaRecorderSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    typeof navigator.mediaDevices !== 'undefined' &&
    typeof navigator.mediaDevices.getUserMedia === 'function'
  );
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

async function fetchSessionInfo(
  sessionId: string,
): Promise<{ displayName: string | null; questionText: string }> {
  try {
    const res = await fetch(`${API_BASE}/interviews/public/${sessionId}/info`);
    if (res.ok) {
      const data = (await res.json()) as {
        display_name?: string | null;
        questions?: Array<{ text?: string; question?: string } | string>;
      };
      const q = data.questions?.[0];
      const questionText =
        typeof q === 'string'
          ? q
          : q && typeof q === 'object'
            ? (q.text ?? q.question ?? '')
            : '';
      return { displayName: data.display_name ?? null, questionText: questionText || initialState.questionText };
    }
  } catch {
    // Silently fall back — session info endpoint may not exist in slice
  }
  return { displayName: null, questionText: initialState.questionText };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function InterviewSession() {
  const { sessionId = '' } = useParams<{ sessionId: string }>();
  const [state, dispatch] = useReducer(reducer, initialState);

  // Refs that survive re-renders
  const streamRef = useRef<MediaStream | null>(null);
  const previewRef = useRef<HTMLVideoElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const blobRef = useRef<Blob | null>(null);
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const micLevelRef = useRef<number>(0);
  const micBarRef = useRef<HTMLDivElement | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const mimeTypeRef = useRef<string>('video/webm;codecs=vp8,opus');

  // ---------------------------------------------------------------------------
  // Fetch session info on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!sessionId) return;
    void fetchSessionInfo(sessionId).then(({ displayName, questionText }) => {
      dispatch({ type: 'SET_SESSION_INFO', displayName, questionText });
    });
  }, [sessionId]);

  // ---------------------------------------------------------------------------
  // Check browser support on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!isMediaRecorderSupported()) {
      dispatch({ type: 'SET_PHASE', phase: 'unsupported-browser' });
    }
  }, []);

  // ---------------------------------------------------------------------------
  // beforeunload guard
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const phase = state.phase;
    const shouldWarn = phase === 'recording' || phase === 'uploading' || phase === 'auto-stopped';
    if (!shouldWarn) return;

    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = 'Your recording is in progress. Are you sure you want to leave?';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [state.phase]);

  // ---------------------------------------------------------------------------
  // Cleanup on unmount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    return () => {
      if (tickerRef.current) clearInterval(tickerRef.current);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Mic level meter via Web Audio AnalyserNode
  // ---------------------------------------------------------------------------
  const startMicMeter = useCallback((stream: MediaStream) => {
    try {
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        micLevelRef.current = avg;
        if (micBarRef.current) {
          const pct = Math.min(100, (avg / 128) * 100);
          micBarRef.current.style.width = `${pct}%`;
        }
        animFrameRef.current = requestAnimationFrame(tick);
      };
      animFrameRef.current = requestAnimationFrame(tick);
    } catch {
      // AudioContext not available — meter is decorative, continue without it
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Request permissions
  // ---------------------------------------------------------------------------
  const requestPermissions = useCallback(async () => {
    if (!isMediaRecorderSupported()) {
      dispatch({ type: 'SET_PHASE', phase: 'unsupported-browser' });
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      dispatch({ type: 'SET_PHASE', phase: 'ready-check' });

      // Attach stream to preview video element (may render after this tick)
      requestAnimationFrame(() => {
        if (previewRef.current) {
          previewRef.current.srcObject = stream;
        }
      });
      startMicMeter(stream);
    } catch {
      dispatch({ type: 'SET_PHASE', phase: 'permission-denied' });
    }
  }, [startMicMeter]);

  // Attach stream when previewRef becomes available (readyCheck phase)
  const setPreviewRef = useCallback(
    (el: HTMLVideoElement | null) => {
      previewRef.current = el;
      if (el && streamRef.current) {
        el.srcObject = streamRef.current;
      }
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Start recording (consumes attempt)
  // ---------------------------------------------------------------------------
  const startRecording = useCallback(async () => {
    if (!streamRef.current) return;

    // D3 attempt-lock: consume attempt before recording starts
    try {
      await startAnswerAttempt(sessionId, 0);
    } catch (err: unknown) {
      const e = err as { status?: number };
      if (e.status === 409) {
        dispatch({ type: 'SET_PHASE', phase: 'attempt-used' });
        return;
      }
      // Non-409 errors: warn but proceed (slice behaviour — full product would block)
      console.warn('start-attempt endpoint error:', err);
    }

    // Determine supported mime type
    const candidates = [
      'video/webm;codecs=vp8,opus',
      'video/webm;codecs=vp9,opus',
      'video/webm',
      'video/mp4',
    ];
    const mime = candidates.find((m) => MediaRecorder.isTypeSupported(m)) ?? '';
    mimeTypeRef.current = mime || 'video/webm';

    const recorder = new MediaRecorder(streamRef.current, mime ? { mimeType: mime } : {});
    recorderRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = () => {
      blobRef.current = new Blob(chunksRef.current, { type: mimeTypeRef.current || 'video/webm' });
      void performUpload();
    };

    recorder.start(1000); // collect data every 1 s
    dispatch({ type: 'SET_PHASE', phase: 'recording' });

    // Countdown ticker
    tickerRef.current = setInterval(() => {
      dispatch({ type: 'TICK' });
    }, 1000);

    // Auto-stop at 2 min
    setTimeout(() => {
      if (recorderRef.current?.state === 'recording') {
        recorderRef.current.stop();
        if (tickerRef.current) clearInterval(tickerRef.current);
        dispatch({ type: 'SET_PHASE', phase: 'auto-stopped' });
      }
    }, MAX_SECONDS * 1000);
  }, [sessionId]);

  // ---------------------------------------------------------------------------
  // Stop recording manually
  // ---------------------------------------------------------------------------
  const stopRecording = useCallback(() => {
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop();
    }
    if (tickerRef.current) clearInterval(tickerRef.current);
    dispatch({ type: 'SET_PHASE', phase: 'uploading' });
    // onstop fires async — blob will be ready before upload kicks off
  }, []);

  // ---------------------------------------------------------------------------
  // Upload blob
  // ---------------------------------------------------------------------------
  const performUpload = useCallback(async () => {
    const blob = blobRef.current;
    if (!blob) {
      dispatch({ type: 'SET_UPLOAD_ERROR', error: 'No recording data found.' });
      return;
    }
    dispatch({ type: 'SET_PHASE', phase: 'uploading' });
    dispatch({ type: 'SET_UPLOAD_PCT', pct: 0 });

    const contentType = mimeTypeRef.current || 'video/webm';

    try {
      const { url, fields, file_id } = await getUploadUrl(contentType);
      await uploadVideoBlob(url, fields, file_id, blob, contentType, (pct) => {
        dispatch({ type: 'SET_UPLOAD_PCT', pct });
      });
      // Stop camera stream after successful upload
      streamRef.current?.getTracks().forEach((t) => t.stop());
      dispatch({ type: 'SET_PHASE', phase: 'submitted' });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload error';
      dispatch({ type: 'SET_UPLOAD_ERROR', error: msg });
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Retry upload (same blob)
  // ---------------------------------------------------------------------------
  const retryUpload = useCallback(() => {
    void performUpload();
  }, [performUpload]);

  // When auto-stopped, trigger upload after recorder onstop fires
  // (onstop already calls performUpload; this phase is intermediate display)

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------
  const { phase, secondsLeft, uploadPct, uploadError, displayName, questionText } = state;

  const contactLink = (
    <a
      href="mailto:support@hiringteam.com"
      style={styles.link}
    >
      Contact the hiring team
    </a>
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div style={styles.root}>
      <style>{cssReset}</style>

      {/* D6 White-label header */}
      <header style={styles.header}>
        <span style={styles.headerLogo}>{displayName || 'Hiring Team'}</span>
      </header>

      <main style={styles.main}>
        {/* ── permission-prompt ── */}
        {phase === 'permission-prompt' && (
          <Screen>
            <Heading>Before we begin</Heading>
            <Body>
              This interview requires your camera and microphone. When you click the button below,
              your browser will ask for permission.
            </Body>
            <Body style={{ marginTop: 8 }}>
              Your video is recorded and stored securely — it will only be reviewed by the hiring
              team.
            </Body>
            <Btn onClick={() => void requestPermissions()}>Allow camera &amp; microphone</Btn>
          </Screen>
        )}

        {/* ── permission-denied ── */}
        {phase === 'permission-denied' && (
          <Screen>
            <Heading>Camera access required</Heading>
            <Body>
              We couldn't access your camera or microphone. This usually means you clicked "Block"
              or your device has restricted access.
            </Body>
            <Body style={{ marginTop: 8 }}>
              To fix this, open your browser settings, find camera permissions for this site, and
              set them to "Allow". Then reload the page.
            </Body>
            <Body style={{ marginTop: 16 }}>
              If you need help, {contactLink}.
            </Body>
          </Screen>
        )}

        {/* ── unsupported-browser ── */}
        {phase === 'unsupported-browser' && (
          <Screen>
            <Heading>Use Chrome or Safari</Heading>
            <Body>
              Your current browser doesn't support video recording. Please open this link in Google
              Chrome or Safari to continue.
            </Body>
            <Body style={{ marginTop: 16 }}>
              Need assistance? {contactLink}.
            </Body>
          </Screen>
        )}

        {/* ── ready-check (D4) ── */}
        {phase === 'ready-check' && (
          <Screen>
            <Heading>Ready check</Heading>
            <Body style={{ marginBottom: 4 }}>
              <strong>Make sure you can see yourself clearly and your microphone is working.</strong>
            </Body>

            {/* Live cam preview */}
            <div style={styles.previewWrap}>
              <video
                ref={setPreviewRef}
                autoPlay
                muted
                playsInline
                style={styles.preview}
                aria-label="Camera preview"
              />
            </div>

            {/* Mic level meter */}
            <div style={styles.meterWrap} aria-label="Microphone level">
              <div style={styles.meterTrack}>
                <div ref={micBarRef} style={styles.meterBar} />
              </div>
              <span style={styles.meterLabel}>Mic level</span>
            </div>

            {/* Question preview */}
            <div style={styles.questionBox}>
              <span style={styles.questionLabel}>Your question</span>
              <p style={styles.questionText}>{questionText}</p>
            </div>

            {/* D2 single-take warning */}
            <div style={styles.warningBox} role="note">
              <strong>One take only.</strong> Start when you're ready — you won't be able to
              re-record.
            </div>

            <Btn onClick={() => void startRecording()}>I'm ready — start recording</Btn>
          </Screen>
        )}

        {/* ── recording ── */}
        {phase === 'recording' && (
          <Screen>
            {/* aria-live region for screen readers */}
            <div
              aria-live="polite"
              aria-atomic="true"
              style={{ position: 'absolute', left: -9999, top: 0 }}
            >
              {`Recording in progress. ${formatTime(secondsLeft)} remaining.`}
            </div>

            <div style={styles.recHeader}>
              <RecDot />
              <span style={styles.recLabel}>Recording</span>
            </div>

            <div style={styles.questionBox}>
              <span style={styles.questionLabel}>Your question</span>
              <p style={styles.questionText}>{questionText}</p>
            </div>

            <div style={styles.timerDisplay} aria-hidden="true">
              {formatTime(secondsLeft)}
            </div>

            <Btn onClick={stopRecording} style={styles.stopBtn}>
              Stop recording
            </Btn>
          </Screen>
        )}

        {/* ── auto-stopped ── */}
        {phase === 'auto-stopped' && (
          <Screen>
            <Heading>Time's up</Heading>
            <Body>Your recording has stopped. Uploading now&hellip;</Body>
            <ProgressBar pct={uploadPct} />
          </Screen>
        )}

        {/* ── uploading ── */}
        {phase === 'uploading' && (
          <Screen>
            <Heading>Uploading your response</Heading>
            <Body>
              <strong>Don't close this tab</strong> — your video is being saved.
            </Body>
            <ProgressBar pct={uploadPct} />
            <Body style={{ marginTop: 12, fontSize: 14, color: '#6b7280' }}>
              This usually takes less than a minute. Your response is encrypted in transit.
            </Body>
          </Screen>
        )}

        {/* ── upload-failed ── */}
        {phase === 'upload-failed' && (
          <Screen>
            <Heading>Upload didn't finish</Heading>
            <Body>
              {uploadError || 'Something went wrong while saving your video.'}
            </Body>
            <Body style={{ marginTop: 8 }}>
              Your recording is still saved in this tab. You can try again — your answer won't be
              lost.
            </Body>
            <Btn onClick={retryUpload}>Retry upload</Btn>
            <Body style={{ marginTop: 16, fontSize: 14 }}>
              If the problem persists, {contactLink}.
            </Body>
          </Screen>
        )}

        {/* ── attempt-used ── */}
        {phase === 'attempt-used' && (
          <Screen>
            <Heading>Attempt already recorded</Heading>
            <Body>
              Your answer for this question has already been submitted. Each question allows one
              attempt only.
            </Body>
            <Body style={{ marginTop: 8 }}>
              If you believe this is an error, {contactLink}.
            </Body>
          </Screen>
        )}

        {/* ── submitted ── */}
        {phase === 'submitted' && (
          <Screen>
            <div style={styles.successIcon} aria-hidden="true">✓</div>
            <Heading>Response submitted</Heading>
            <Body>
              Your video answer has been received. The hiring team will review it and be in touch.
            </Body>
            <div style={styles.nextStepsBox}>
              <strong style={{ display: 'block', marginBottom: 8 }}>What happens next</strong>
              <ol style={{ paddingLeft: 20, margin: 0, lineHeight: 1.7 }}>
                <li>Your response is reviewed by the hiring team.</li>
                <li>You'll receive an email update within a few business days.</li>
                <li>If selected, you'll be invited to the next stage.</li>
              </ol>
            </div>
            <Body style={{ marginTop: 16, color: '#6b7280', fontSize: 14 }}>
              This tab is safe to close.
            </Body>
          </Screen>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Screen({ children }: { children: React.ReactNode }) {
  return <div style={styles.screen}>{children}</div>;
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h1 style={styles.heading}>{children}</h1>;
}

function Body({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <p style={{ ...styles.body, ...style }}>{children}</p>;
}

function Btn({
  children,
  onClick,
  style,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <button type="button" onClick={onClick} style={{ ...styles.btn, ...style }}>
      {children}
    </button>
  );
}

function RecDot() {
  return (
    <span
      style={styles.recDot}
      aria-hidden="true"
    />
  );
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div style={styles.progressTrack} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div style={{ ...styles.progressFill, width: `${pct}%` }} />
      <span style={styles.progressLabel}>{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  root: {
    minHeight: '100vh',
    background: '#f7f8fc',
    fontFamily: "'Fira Sans', 'Segoe UI', system-ui, -apple-system, Arial, sans-serif",
    color: '#1f2937',
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    background: '#ffffff',
    borderBottom: '1px solid #e5e7eb',
    padding: '14px 20px',
    display: 'flex',
    alignItems: 'center',
  },
  headerLogo: {
    fontSize: 18,
    fontWeight: 700,
    color: '#5b6af5',
    letterSpacing: '-0.3px',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '24px 16px 40px',
  },
  screen: {
    width: '100%',
    maxWidth: 480,
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
  },
  heading: {
    fontSize: 26,
    fontWeight: 700,
    color: '#111827',
    margin: '0 0 16px',
    lineHeight: 1.25,
  },
  body: {
    fontSize: 16,
    lineHeight: 1.65,
    color: '#374151',
    margin: '0 0 8px',
  },
  btn: {
    display: 'inline-block',
    marginTop: 24,
    padding: '14px 28px',
    background: '#5b6af5',
    color: '#ffffff',
    fontSize: 16,
    fontWeight: 600,
    border: 'none',
    borderRadius: 10,
    cursor: 'pointer',
    minHeight: 48,
    minWidth: 180,
    letterSpacing: '0.01em',
    boxShadow: '0 1px 4px rgba(91,106,245,0.3)',
    transition: 'background 0.15s',
    textAlign: 'center' as const,
    width: '100%',
  },
  stopBtn: {
    background: '#dc2626',
    boxShadow: '0 1px 4px rgba(220,38,38,0.3)',
    marginTop: 32,
  },
  link: {
    color: '#5b6af5',
    textDecoration: 'underline',
  },
  previewWrap: {
    width: '100%',
    borderRadius: 12,
    overflow: 'hidden',
    background: '#1f2937',
    aspectRatio: '16/9',
    marginBottom: 16,
  },
  preview: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    display: 'block',
    transform: 'scaleX(-1)', // mirror effect
  },
  meterWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 20,
  },
  meterTrack: {
    flex: 1,
    height: 8,
    background: '#e5e7eb',
    borderRadius: 4,
    overflow: 'hidden',
  },
  meterBar: {
    height: '100%',
    background: '#5b6af5',
    borderRadius: 4,
    width: '0%',
    transition: 'width 0.08s',
  },
  meterLabel: {
    fontSize: 12,
    color: '#6b7280',
    whiteSpace: 'nowrap' as const,
    minWidth: 60,
  },
  questionBox: {
    background: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: 10,
    padding: '16px 20px',
    marginBottom: 16,
  },
  questionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.08em',
    color: '#9ca3af',
    display: 'block',
    marginBottom: 6,
  },
  questionText: {
    fontSize: 18,
    lineHeight: 1.55,
    color: '#111827',
    margin: 0,
    fontWeight: 500,
  },
  warningBox: {
    background: '#fef9c3',
    border: '1px solid #fde047',
    borderRadius: 8,
    padding: '12px 16px',
    fontSize: 14,
    color: '#713f12',
    marginBottom: 4,
  },
  recHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 24,
  },
  recDot: {
    display: 'inline-block',
    width: 14,
    height: 14,
    borderRadius: '50%',
    background: '#dc2626',
    animation: 'rec-pulse 1.2s ease-in-out infinite',
  },
  recLabel: {
    fontSize: 15,
    fontWeight: 600,
    color: '#dc2626',
    letterSpacing: '0.04em',
    textTransform: 'uppercase' as const,
  },
  timerDisplay: {
    fontSize: 52,
    fontWeight: 700,
    color: '#111827',
    textAlign: 'center' as const,
    letterSpacing: '-1px',
    margin: '8px 0 0',
    fontVariantNumeric: 'tabular-nums',
  },
  progressTrack: {
    position: 'relative' as const,
    height: 12,
    background: '#e5e7eb',
    borderRadius: 6,
    overflow: 'hidden',
    marginTop: 20,
  },
  progressFill: {
    height: '100%',
    background: '#5b6af5',
    borderRadius: 6,
    transition: 'width 0.2s',
  },
  progressLabel: {
    position: 'absolute' as const,
    right: 8,
    top: '50%',
    transform: 'translateY(-50%)',
    fontSize: 10,
    fontWeight: 700,
    color: '#374151',
  },
  successIcon: {
    width: 56,
    height: 56,
    borderRadius: '50%',
    background: '#d1fae5',
    color: '#065f46',
    fontSize: 28,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    fontWeight: 700,
  },
  nextStepsBox: {
    background: '#f0f4ff',
    border: '1px solid #c7d2fe',
    borderRadius: 10,
    padding: '16px 20px',
    marginTop: 16,
    fontSize: 15,
    color: '#1e1b4b',
    lineHeight: 1.6,
  },
};

// ---------------------------------------------------------------------------
// CSS reset + keyframe for rec dot pulse
// ---------------------------------------------------------------------------
const cssReset = `
  *, *::before, *::after { box-sizing: border-box; }
  body { margin: 0; }

  @keyframes rec-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.85); }
  }

  @media (prefers-reduced-motion: reduce) {
    [style*="rec-pulse"] {
      animation: none !important;
    }
    * {
      animation-duration: 0.001ms !important;
      transition-duration: 0.001ms !important;
    }
  }
`;
