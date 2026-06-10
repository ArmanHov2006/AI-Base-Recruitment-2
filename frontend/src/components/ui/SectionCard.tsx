import { Card } from 'antd';
import type { ReactNode } from 'react';

interface SectionCardProps {
  title?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  style?: React.CSSProperties;
  bodyStyle?: React.CSSProperties;
}

export default function SectionCard({ title, extra, children, style, bodyStyle }: SectionCardProps) {
  return (
    <Card
      title={
        title ? (
          <span style={{ fontFamily: '"Fira Sans", sans-serif', fontWeight: 700, color: '#ededf5', fontSize: 15 }}>
            {title}
          </span>
        ) : undefined
      }
      extra={extra}
      style={{
        marginBottom: 16,
        borderColor: 'rgba(255,255,255,0.08)',
        borderRadius: 'var(--radius-card)',
        background: '#0e0e15',
        ...style,
      }}
      styles={{ body: { ...bodyStyle } }}
    >
      {children}
    </Card>
  );
}
