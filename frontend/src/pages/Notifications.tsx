import { List, Button, Badge, Empty } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getNotifications, markRead, markAllRead } from '../api/notifications';
import type { Notification } from '../types';

const NOTIF_ICONS: Record<string, string> = {
  new_application: '📥',
  stage_change: '↕',
  rating_update: '⭐',
  mention: '@',
};

function notifLink(n: Notification): string | null {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application' && p.job_id) return `/jobs/${p.job_id}`;
  if ((n.type === 'stage_change' || n.type === 'rating_update' || n.type === 'mention') && p.candidate_id)
    return `/candidates/${p.candidate_id}`;
  return null;
}

function formatTitle(n: Notification): string {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application') return `New application for "${p.job_title ?? 'a job'}"`;
  if (n.type === 'stage_change')
    return `Stage → ${p.new_stage ?? '?'} for ${p.candidate_name ?? 'candidate'} (${p.job_title ?? ''})`;
  if (n.type === 'rating_update')
    return `Rating submitted for ${p.candidate_name ?? 'candidate'} — ${p.job_title ?? ''}`;
  if (n.type === 'mention')
    return `${p.mentioned_by_name ?? 'Someone'} mentioned you on ${p.candidate_name ?? 'a candidate'}`;
  return n.type;
}

function timeAgo(iso: string): string {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function Notifications() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', 'all'],
    queryFn: () => getNotifications({ limit: 50 }),
  });

  const markReadMutation = useMutation({
    mutationFn: markRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });

  const markAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });

  const items = data?.items ?? [];
  const unread = data?.unread_count ?? 0;

  const handleClick = (item: Notification) => {
    if (!item.read_at) markReadMutation.mutate(item.id);
    const link = notifLink(item);
    if (link) navigate(link);
  };

  return (
    <div className="page-shell">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <BellOutlined style={{ fontSize: 18, color: '#5b6af5' }} />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Notifications</h2>
          {unread > 0 && <Badge count={unread} />}
        </div>
        {unread > 0 && (
          <Button
            size="small"
            onClick={() => markAllMutation.mutate()}
            loading={markAllMutation.isPending}
          >
            Mark all read
          </Button>
        )}
      </div>

      <div className="data-panel">
        {items.length === 0 && !isLoading ? (
          <Empty description="No notifications" style={{ padding: '48px 0' }} />
        ) : (
          <List
            loading={isLoading}
            dataSource={items}
            renderItem={(item) => (
              <List.Item
                onClick={() => handleClick(item)}
                style={{
                  cursor: notifLink(item) ? 'pointer' : 'default',
                  padding: '12px 16px',
                  background: item.read_at ? 'transparent' : 'rgba(91,106,245,0.06)',
                  borderLeft: item.read_at ? '3px solid transparent' : '3px solid #5b6af5',
                  transition: 'background 0.15s',
                }}
              >
                <List.Item.Meta
                  avatar={
                    <span style={{ fontSize: 16, opacity: item.read_at ? 0.45 : 1 }}>
                      {NOTIF_ICONS[item.type] ?? '🔔'}
                    </span>
                  }
                  title={
                    <span style={{ fontWeight: item.read_at ? 500 : 700, fontSize: 14 }}>
                      {formatTitle(item)}
                    </span>
                  }
                  description={
                    <span style={{ fontSize: 12, color: '#64648a' }}>{timeAgo(item.created_at)}</span>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );
}
