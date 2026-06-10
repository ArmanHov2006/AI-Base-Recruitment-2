import { useState, useCallback, useEffect } from 'react';
import { List, Button, Empty, Spin, message } from 'antd';
import {
  BellOutlined,
  FileAddOutlined,
  ProjectOutlined,
  StarOutlined,
  CommentOutlined,
  SafetyCertificateOutlined,
  LockOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getNotifications, markAllRead, markRead } from '../api/notifications';
import type { Notification } from '../types';

function notifIcon(type: string): React.ReactNode {
  if (type === 'new_application') return <FileAddOutlined style={{ color: '#5b6af5', fontSize: 16 }} />;
  if (type === 'stage_change') return <ProjectOutlined style={{ color: '#fbbf24', fontSize: 16 }} />;
  if (type === 'rating_update') return <StarOutlined style={{ color: '#34d399', fontSize: 16 }} />;
  if (type === 'mention') return <CommentOutlined style={{ color: '#a855f7', fontSize: 16 }} />;
  if (type === 'role_changed') return <SafetyCertificateOutlined style={{ color: '#f97316', fontSize: 16 }} />;
  if (type === 'account_status_changed') return <LockOutlined style={{ color: '#f87171', fontSize: 16 }} />;
  if (type === 'interview_scheduled' || type === 'interview_reminder') return <ProjectOutlined style={{ color: '#34d399', fontSize: 16 }} />;
  return <BellOutlined style={{ color: '#a1a1bb', fontSize: 16 }} />;
}

function formatNotifTitle(n: Notification): string {
  const p = n.payload as Record<string, unknown>;
  if (n.type === 'new_application') return `New application for "${p.job_title ?? 'a job'}"`;
  if (n.type === 'stage_change') {
    return `${p.candidate_name ?? 'Candidate'} moved to ${p.new_stage ?? '?'} — ${p.job_title ?? ''}`;
  }
  if (n.type === 'rating_update') {
    return `Rating submitted for ${p.candidate_name ?? 'candidate'} — ${p.job_title ?? ''}`;
  }
  if (n.type === 'mention') return 'You were mentioned in a candidate note';
  if (n.type === 'role_changed') {
    return `Your role was changed from ${p.old_role ?? '?'} to ${p.new_role ?? '?'} by ${p.changed_by ?? 'admin'}`;
  }
  if (n.type === 'account_status_changed') {
    const active = p.is_active === true || p.is_active === 'true';
    return `Your account was ${active ? 'activated' : 'deactivated'} by ${p.changed_by ?? 'admin'}`;
  }
  if (n.type === 'interview_scheduled') {
    let when = '';
    if (p.interview_scheduled_at) {
      const d = new Date(p.interview_scheduled_at as string);
      when = isNaN(d.getTime()) ? '' : d.toLocaleString();
    }
    return `Interview scheduled for ${p.candidate_name ?? 'candidate'}${when ? ` — ${when}` : ''}`;
  }
  if (n.type === 'interview_reminder') {
    let when = '';
    if (p.interview_scheduled_at) {
      const d = new Date(p.interview_scheduled_at as string);
      when = isNaN(d.getTime()) ? '' : d.toLocaleString();
    }
    return `Interview reminder: ${p.candidate_name ?? 'candidate'}${when ? ` at ${when}` : ''}`;
  }
  return n.type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function notifNavTarget(n: Notification): string | null {
  const p = n.payload as Record<string, string>;
  if (n.type === 'mention' && p.candidate_id) return `/candidates/${p.candidate_id}`;
  if ((n.type === 'stage_change' || n.type === 'rating_update') && p.candidate_id) {
    return `/candidates/${p.candidate_id}`;
  }
  return null;
}

function formatRelativeTime(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const data = await getNotifications({ limit: 50 });
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch {
      message.error('Failed to load notifications');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleMarkAllRead = async () => {
    try {
      await markAllRead();
      setUnreadCount(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, read_at: new Date().toISOString() })));
    } catch {
      message.error('Failed to mark all as read');
    }
  };

  const handleItemClick = async (item: Notification) => {
    if (!item.read_at) {
      try {
        await markRead(item.id);
        setNotifications((prev) =>
          prev.map((n) => n.id === item.id ? { ...n, read_at: new Date().toISOString() } : n)
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      } catch {
        // non-critical
      }
    }
    const target = notifNavTarget(item);
    if (target) navigate(target);
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 680, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <span style={{ color: '#64648a', fontSize: 13 }}>
          {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
        </span>
        {unreadCount > 0 && (
          <Button type="link" size="small" onClick={handleMarkAllRead} style={{ padding: 0, color: '#5b6af5' }}>
            Mark all read
          </Button>
        )}
      </div>

      {notifications.length === 0 ? (
        <Empty description="No notifications" style={{ paddingTop: 64 }} />
      ) : (
        <List
          dataSource={notifications}
          renderItem={(item) => {
            const target = notifNavTarget(item);
            return (
              <List.Item
                onClick={() => handleItemClick(item)}
                role={target ? 'button' : undefined}
                tabIndex={target ? 0 : undefined}
                onKeyDown={
                  target
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleItemClick(item);
                        }
                      }
                    : undefined
                }
                style={{
                  cursor: target ? 'pointer' : 'default',
                  background: item.read_at ? 'transparent' : 'rgba(91,106,245,0.06)',
                  borderRadius: 8,
                  padding: '12px 16px',
                  marginBottom: 4,
                  borderBottom: 'none',
                  transition: 'background 0.15s',
                }}
                className="notification-item"
              >
                <List.Item.Meta
                  avatar={
                    <span style={{ display: 'flex', alignItems: 'center', paddingTop: 3 }}>
                      {notifIcon(item.type)}
                    </span>
                  }
                  title={
                    <span style={{ fontSize: 14, fontWeight: item.read_at ? 500 : 700, color: '#ededf5' }}>
                      {formatNotifTitle(item)}
                    </span>
                  }
                  description={
                    <span style={{ fontSize: 12, color: '#64648a' }}>
                      {formatRelativeTime(item.created_at)}
                    </span>
                  }
                />
                {!item.read_at && (
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: '#5b6af5',
                      flexShrink: 0,
                      marginLeft: 12,
                    }}
                  />
                )}
              </List.Item>
            );
          }}
        />
      )}
    </div>
  );
}
