import { Button, Alert } from 'antd';
import { CheckCircleOutlined, FileSearchOutlined, ProfileOutlined, SafetyCertificateOutlined } from '@ant-design/icons';

interface StepParsingProps {
  isParsing: boolean;
  error: Error | null;
  onRetry: () => void;
}

export default function StepParsing({ isParsing: _isParsing, error, onRetry }: StepParsingProps) {
  if (error) {
    const isTimeout = error.message?.includes('504');
    const isParseError = error.message?.includes('502');

    const description = isTimeout
      ? 'The AI is taking too long to process this resume. Please try again.'
      : isParseError
      ? 'Could not extract structured data from this resume. Please try again or upload a different file.'
      : error.message || 'An error occurred while parsing the resume.';

    return (
      <div style={{ padding: '40px 0' }}>
        <Alert
          type="error"
          message="Parsing Failed"
          description={description}
          showIcon
          style={{ marginBottom: 24 }}
        />
        <div style={{ textAlign: 'center' }}>
          <Button type="primary" onClick={onRetry}>
            Retry Parsing
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="parsing-state" aria-live="polite">
      <div className="parsing-rail">
        <div className="parsing-step is-done">
          <CheckCircleOutlined />
          <span>Reading file</span>
        </div>
        <div className="parsing-step is-active">
          <ProfileOutlined />
          <span>Extracting profile</span>
        </div>
        <div className="parsing-step">
          <SafetyCertificateOutlined />
          <span>Checking fields</span>
        </div>
      </div>

      <div className="parse-skeleton">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <FileSearchOutlined style={{ color: '#5b6af5', fontSize: 20 }} />
          <div>
            <strong style={{ color: '#ededf5' }}>Building candidate profile</strong>
            <div style={{ color: '#a1a1bb', fontSize: 13 }}>
              This usually takes a few moments.
            </div>
          </div>
        </div>
        <div className="parse-skeleton-block" style={{ width: '58%' }} />
        <div className="parse-skeleton-block" style={{ width: '84%' }} />
        <div className="parse-skeleton-block" style={{ width: '72%' }} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 4 }}>
          <div className="parse-skeleton-block" />
          <div className="parse-skeleton-block" />
        </div>
      </div>
    </div>
  );
}
