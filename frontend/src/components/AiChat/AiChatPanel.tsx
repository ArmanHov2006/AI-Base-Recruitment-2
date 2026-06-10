import { useEffect, useRef, useState } from 'react';
import { Card, Input, Button, Alert, Empty } from 'antd';
import { RobotOutlined, UserOutlined, SendOutlined } from '@ant-design/icons';
import { streamChat } from '../../api/ai';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface AiChatPanelProps {
  candidateId: string;
}

export default function AiChatPanel({ candidateId }: AiChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    setError(null);
    setInput('');
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '' },
    ]);
    setStreaming(true);

    try {
      await streamChat({
        candidateId,
        message: text,
        onToken: (chunk) => {
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { role: 'assistant', content: last.content + chunk };
            return copy;
          });
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Chat request failed');
      // Drop the empty assistant placeholder if nothing streamed in.
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && last.content === '') {
          return prev.slice(0, -1);
        }
        return prev;
      });
    } finally {
      setStreaming(false);
    }
  };

  return (
    <Card
      title={
        <span>
          <RobotOutlined style={{ marginRight: 8 }} />
          Ask AI about this candidate
        </span>
      }
      style={{ marginBottom: 16 }}
    >
      <div
        ref={scrollRef}
        style={{
          maxHeight: 320,
          overflowY: 'auto',
          marginBottom: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {messages.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="Ask anything grounded in this candidate's profile — e.g. “Summarize their fit for a backend role.”"
          />
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 8,
                flexDirection: m.role === 'user' ? 'row-reverse' : 'row',
              }}
            >
              <div
                style={{
                  flex: '0 0 auto',
                  color: m.role === 'user' ? '#1677ff' : '#52c41a',
                  marginTop: 2,
                }}
              >
                {m.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
              </div>
              <div
                style={{
                  background: m.role === 'user' ? '#e6f4ff' : '#f6ffed',
                  borderRadius: 8,
                  padding: '8px 12px',
                  maxWidth: '85%',
                  whiteSpace: 'pre-wrap',
                  color: '#333',
                }}
              >
                {m.content || (streaming ? '…' : '')}
              </div>
            </div>
          ))
        )}
      </div>

      {error && (
        <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Ask a question about this candidate…"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={streaming}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={send}
          loading={streaming}
          disabled={!input.trim()}
        >
          Ask
        </Button>
      </div>
    </Card>
  );
}
