import type { ReactNode } from 'react';
import { BankOutlined, SafetyCertificateOutlined } from '@ant-design/icons';

interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Accessible label for the form region. Defaults to the title. */
  formLabel?: string;
}

/**
 * Shared split-screen shell for every public auth page (sign in, register,
 * reset, verify). The left visual panel is constant; pages supply only the
 * form card body via `children`.
 */
export default function AuthLayout({ title, subtitle, children, formLabel }: AuthLayoutProps) {
  return (
    <main className="auth-shell">
      <section className="auth-visual" aria-label="AI Recruitment workspace">
        <div className="auth-brand">
          <div className="brand-mark">
            <BankOutlined />
          </div>
          <div className="auth-brand-text">
            <span>Ardshinbank</span>
            <strong>AI Recruitment</strong>
          </div>
        </div>

        <div className="auth-copy">
          <span>Hiring command center</span>
          <h1>Structured hiring decisions for every role.</h1>
          <p>Secure AI-assisted recruiting for Ardshinbank teams.</p>
        </div>

        <div className="auth-preview" aria-hidden="true">
          <div className="auth-preview-panel">
            <div className="preview-heading">
              <strong>Candidate review</strong>
              <span>Live queue</span>
            </div>
            <div className="preview-row">
              <strong>Senior Backend Engineer</strong>
              <span>Reviewing</span>
              <small>92 match</small>
            </div>
            <div className="preview-row">
              <strong>Data Analyst</strong>
              <span>Shortlist</span>
              <small>87 match</small>
            </div>
            <div className="preview-row">
              <strong>Risk Platform Lead</strong>
              <span>Interview</span>
              <small>84 match</small>
            </div>
          </div>
          <div className="auth-preview-card">
            <SafetyCertificateOutlined style={{ color: '#86EFAC', fontSize: 24 }} />
            <span>Governed access</span>
            <strong>Role based</strong>
            <small>Recruiter, manager, and viewer permissions stay separated.</small>
          </div>
        </div>
      </section>

      <section className="auth-form-wrap" aria-label={formLabel ?? title}>
        <div className="auth-card">
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
          {children}
        </div>
      </section>
    </main>
  );
}
