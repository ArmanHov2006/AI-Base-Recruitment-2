import { useState, useEffect, useCallback, useRef } from 'react';
import { getAccessToken } from '../../api/client';
import {
  Layout,
  Badge,
  Popover,
  List,
  Button,
  Tooltip,
} from 'antd';
import {
  AppstoreOutlined,
  UserOutlined,
  SolutionOutlined,
  SearchOutlined,
  BellOutlined,
  PlusOutlined,
  LogoutOutlined,
  UserSwitchOutlined,
  AuditOutlined,
} from '@ant-design/icons';
import { useAuth } from '../../context/AuthContext';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { getNotifications, markRead as markNotificationRead, markAllRead as markAllNotificationsRead } from '../../api/notifications';
import type { Notification } from '../../types';
import CommandPalette from '../CommandPalette';

const { Header, Sider, Content } = Layout;

const SIDEBAR_W = 56;

interface NavItem {
  key: string;
  icon: React.ReactNode;
  label: string;
  adminOnly?: boolean;
}

const BASE_NAV: NavItem[] = [
  { key: '/analytics', icon: <AppstoreOutlined />, label: 'Overview' },
  { key: '/', icon: <UserOutlined />, label: 'Candidates' },
  { key: '/jobs', icon: <SolutionOutlined />, label: 'Jobs' },
];

const ADMIN_NAV: NavItem[] = [
  { key: '/admin/users', icon: <UserSwitchOutlined />, label: 'User Management', adminOnly: true },
  { key: '/admin/audit', icon: <AuditOutlined />, label: 'Audit Log', adminOnly: true },
];

const PAGE_META: Record<string, { title: string; subtitle: string }> = {
  '/analytics': { title: 'Overview', subtitle: 'Q2 2026 · Analytics' },
  '/': { title: 'Candidates', subtitle: 'AI-ranked' },
  '/jobs': { title: 'Jobs', subtitle: 'Open roles' },
  '/admin/users': { title: 'User Management', subtitle: 'Administration' },
  '/admin/audit': { title: 'Audit Log', subtitle: 'Administration' },
  '/notifications': { title: 'Notifications', subtitle: '' },
  '/pipeline': { title: 'Pipeline', subtitle: 'Recruitment board' },
};

function getNavKey(pathname: string): string {
  if (pathname === '/' || pathname.startsWith('/candidates')) return '/';
  if (pathname.startsWith('/analytics')) return '/analytics';
  if (pathname.startsWith('/admin/audit')) return '/admin/audit';
  if (pathname.startsWith('/admin')) return '/admin/users';
  if (pathname.startsWith('/jobs') && !pathname.includes('/pipeline')) return '/jobs';
  if (pathname.startsWith('/pipeline') || pathname.includes('/pipeline')) return '/pipeline';
  return pathname;
}

function getPageMeta(pathname: string): { title: string; subtitle: string } {
  if (pathname.startsWith('/jobs') && pathname.includes('/compare')) {
    return { title: 'Compare', subtitle: 'Side-by-side evaluation' };
  }
  if (pathname.startsWith('/jobs') && pathname.includes('/leaderboard')) {
    return { title: 'Leaderboard', subtitle: 'Top-ranked candidates' };
  }
  if (pathname.startsWith('/jobs') && pathname.includes('/role-analytics')) {
    return { title: 'Role Analytics', subtitle: 'Pipeline health' };
  }
  if (pathname.startsWith('/pipeline') || pathname.includes('/pipeline')) {
    return { title: 'Pipeline', subtitle: 'Recruitment board' };
  }
  if (pathname.match(/^\/candidates\/[^/]+/)) {
    return { title: 'Candidate', subtitle: 'Profile & AI assessment' };
  }
  if (pathname.match(/^\/jobs\/[^/]+$/) ) {
    return { title: 'Job Detail', subtitle: 'Role overview' };
  }
  const key = getNavKey(pathname);
  return PAGE_META[key] || { title: 'Workspace', subtitle: '' };
}

function getInitialsFromString(value?: string | null): string {
  if (!value) return '?';
  const parts = value.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((p) => p[0]?.toUpperCase()).join('');
}

const AVATAR_COLORS = ['#3d4acc', '#10b981', '#7c3aed', '#d97706', '#e11d48'];
function avatarBg(name?: string | null): string {
  if (!name) return AVATAR_COLORS[0];
  const sum = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

const NOTIF_ICONS: Record<string, string> = {
  new_application: '📥',
  stage_change: '↕',
  rating_update: '⭐',
  mention: '@',
};

function getNotifIcon(type: string): string {
  return NOTIF_ICONS[type] ?? '🔔';
}

function formatNotifTitle(n: Notification): string {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application') return `New application for "${p.job_title ?? 'a job'}"`;
  if (n.type === 'stage_change') {
    return `Stage → ${p.new_stage ?? '?'} for ${p.candidate_name ?? 'candidate'} (${p.job_title ?? ''})`;
  }
  if (n.type === 'rating_update') {
    return `Rating submitted for ${p.candidate_name ?? 'candidate'} — ${p.job_title ?? ''}`;
  }
  if (n.type === 'mention') {
    return `${p.mentioned_by_name ?? 'Someone'} mentioned you on ${p.candidate_name ?? 'a candidate'}`;
  }
  return n.type;
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

function getNotifLink(n: Notification): string | null {
  const p = n.payload as Record<string, string>;
  if (n.type === 'new_application' && p.job_id) return `/jobs/${p.job_id}`;
  if (n.type === 'stage_change' && p.candidate_id) return `/candidates/${p.candidate_id}`;
  if (n.type === 'rating_update' && p.candidate_id) return `/candidates/${p.candidate_id}`;
  if (n.type === 'mention' && p.candidate_id) return `/candidates/${p.candidate_id}`;
  return null;
}

export default function AppLayout() {
  const [notifOpen, setNotifOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [bellShaking, setBellShaking] = useState(false);
  const prevUnreadRef = useRef(0);
  const lastSseCountRef = useRef(-1);
  const sseRef = useRef<EventSource | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const isAdmin = user?.role === 'admin';
  const navItems = isAdmin ? [...BASE_NAV, ...ADMIN_NAV] : BASE_NAV;
  const activeKey = getNavKey(location.pathname);
  const pageMeta = getPageMeta(location.pathname);
  const userName = user?.full_name || user?.email || '';

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await getNotifications({ limit: 10 });
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch {
      // keep navigation responsive if notification fetch fails
    }
  }, []);

  const connectSSE = useCallback(() => {
    if (sseRef.current?.readyState === EventSource.OPEN) return;
    sseRef.current?.close();

    const token = getAccessToken();
    if (!token) return;

    const base = (import.meta as { env: Record<string, string> }).env.VITE_API_BASE || 'http://localhost:8000';
    const es = new EventSource(`${base}/notifications/stream?token=${encodeURIComponent(token)}`);
    sseRef.current = es;

    es.onmessage = (e) => {
      const count = parseInt(e.data, 10);
      if (isNaN(count)) return;
      if (count !== lastSseCountRef.current) {
        lastSseCountRef.current = count;
        fetchNotifications();
      }
    };

    es.onerror = () => {
      es.close();
      sseRef.current = null;
    };
  }, [fetchNotifications]);

  useEffect(() => {
    fetchNotifications();
    connectSSE();
    const interval = setInterval(() => {
      fetchNotifications();
      connectSSE();
    }, 30000);
    return () => {
      clearInterval(interval);
      sseRef.current?.close();
    };
  }, [fetchNotifications, connectSSE]);

  useEffect(() => {
    if (unreadCount > prevUnreadRef.current && prevUnreadRef.current !== 0) {
      setBellShaking(true);
      const t = setTimeout(() => setBellShaking(false), 520);
      prevUnreadRef.current = unreadCount;
      return () => clearTimeout(t);
    }
    prevUnreadRef.current = unreadCount;
  }, [unreadCount]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setUnreadCount(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, read_at: new Date().toISOString() })));
    } catch {
      // leave UI unchanged if API call fails
    }
  };

  const handleLogout = async () => {
    setUserMenuOpen(false);
    await logout();
    navigate('/login', { replace: true });
  };

  const handleNotifClick = async (item: Notification) => {
    setNotifOpen(false);
    if (!item.read_at) {
      try {
        await markNotificationRead(item.id);
        setNotifications((prev) =>
          prev.map((n) => (n.id === item.id ? { ...n, read_at: new Date().toISOString() } : n)),
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      } catch {
        // non-fatal — UI already closed
      }
    }
    const link = getNotifLink(item);
    if (link) navigate(link);
  };

  const userMenuContent = (
    <div style={{ minWidth: 160 }}>
      <div style={{ padding: '10px 12px 8px', borderBottom: '1px solid rgba(255,255,255,0.07)', marginBottom: 6 }}>
        <div style={{ color: '#ededf5', fontWeight: 700, fontSize: 13 }}>{user?.full_name || user?.email}</div>
        {user?.role && (
          <div style={{ color: '#64648a', fontSize: 11, marginTop: 2, textTransform: 'uppercase', fontWeight: 800 }}>
            {user.role}
          </div>
        )}
      </div>
      <Button
        type="text"
        icon={<LogoutOutlined />}
        onClick={handleLogout}
        style={{ width: '100%', textAlign: 'left', color: '#a1a1bb', justifyContent: 'flex-start' }}
      >
        Sign out
      </Button>
    </div>
  );

  const notifPanelContent = (
    <div className="notification-panel" style={{ width: 340, maxHeight: 420, overflowY: 'auto' }}>
      <List
        size="small"
        dataSource={notifications}
        locale={{ emptyText: 'No notifications' }}
        renderItem={(item) => (
          <List.Item
            className={`notification-item${item.read_at ? '' : ' is-unread'}`}
            onClick={() => handleNotifClick(item)}
            style={{ cursor: getNotifLink(item) ? 'pointer' : 'default' }}
          >
            <List.Item.Meta
              avatar={
                <span style={{ fontSize: 14, opacity: item.read_at ? 0.5 : 1 }}>
                  {getNotifIcon(item.type)}
                </span>
              }
              title={
                <span style={{ fontSize: 13, fontWeight: item.read_at ? 500 : 700 }}>
                  {formatNotifTitle(item)}
                </span>
              }
              description={
                <span style={{ fontSize: 12, color: '#64648a' }}>
                  {formatRelativeTime(item.created_at)}
                </span>
              }
            />
          </List.Item>
        )}
      />
      {notifications.length > 0 && (
        <div
          style={{
            padding: '8px 12px',
            borderTop: '1px solid rgba(255,255,255,0.07)',
            textAlign: 'center',
          }}
        >
          <Button
            type="link"
            size="small"
            style={{ fontSize: 12, color: '#5b6af5' }}
            onClick={() => { setNotifOpen(false); navigate('/notifications'); }}
          >
            See all notifications
          </Button>
        </div>
      )}
    </div>
  );

  const isPipeline = location.pathname.includes('/pipeline');

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* Sidebar */}
      <Sider
        width={SIDEBAR_W}
        className="app-sider"
        style={{ position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 100 }}
      >
        {/* Logo */}
        <div className="sidebar-logo">
          <span>A</span>
        </div>

        {/* Nav */}
        <nav className="sidebar-nav" aria-label="Main navigation">
          {navItems.map((item) => (
            <Tooltip key={item.key} title={item.label} placement="right" mouseEnterDelay={0.3}>
              <button
                type="button"
                className={`sidebar-nav-btn${activeKey === item.key ? ' is-active' : ''}`}
                onClick={() => navigate(item.key)}
                aria-label={item.label}
                aria-current={activeKey === item.key ? 'page' : undefined}
              >
                {item.icon}
              </button>
            </Tooltip>
          ))}
        </nav>

        {/* Bottom */}
        <div className="sidebar-bottom">
          <Popover
            open={userMenuOpen}
            onOpenChange={setUserMenuOpen}
            trigger="click"
            placement="rightBottom"
            content={userMenuContent}
            overlayStyle={{ zIndex: 200 }}
          >
            <button
              type="button"
              className="sidebar-avatar"
              aria-label="User menu"
              style={{ background: avatarBg(userName) }}
            >
              {getInitialsFromString(userName)}
            </button>
          </Popover>
        </div>
      </Sider>

      {/* Main area */}
      <Layout style={{ marginLeft: SIDEBAR_W }}>
        <Header className="app-header">
          <div className="header-inner">
            <div className="header-left">
              <h1 className="header-page-title">{pageMeta.title}</h1>
              {pageMeta.subtitle && (
                <span className="header-page-subtitle">· {pageMeta.subtitle}</span>
              )}
            </div>

            <div className="header-right">
              <Button
                type="primary"
                icon={<PlusOutlined />}
                className="header-cta-btn"
                onClick={() => navigate('/jobs?create=true')}
                aria-label="New role"
              >
                New role
              </Button>

              <button
                type="button"
                className="cmdk-trigger"
                onClick={() => setPaletteOpen(true)}
                aria-label="Open search"
              >
                <SearchOutlined />
                <span className="cmdk-trigger-label">Search</span>
                <span className="cmdk-kbd">⌘K</span>
              </button>

              <Popover
                open={notifOpen}
                onOpenChange={setNotifOpen}
                trigger="click"
                placement="bottomRight"
                title={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
                    <span>Notifications</span>
                    {unreadCount > 0 && (
                      <Button type="link" size="small" onClick={handleMarkAllRead} style={{ padding: 0 }}>
                        Mark all read
                      </Button>
                    )}
                  </div>
                }
                content={notifPanelContent}
              >
                <Badge count={unreadCount} size="small" offset={[-2, 2]}>
                  <button
                    type="button"
                    className="header-icon-btn"
                    aria-label="Notifications"
                  >
                    <BellOutlined
                      style={{ fontSize: 17 }}
                      className={bellShaking ? 'bell-shake' : undefined}
                    />
                  </button>
                </Badge>
              </Popover>
            </div>
          </div>
        </Header>

        <Content className="app-content">
          <div className={`app-content-inner${isPipeline ? ' is-pipeline-page' : ''}`}>
            <div key={location.key} className="page-animate">
              <Outlet />
            </div>
          </div>
        </Content>
      </Layout>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        isAdmin={isAdmin}
      />
    </Layout>
  );
}
