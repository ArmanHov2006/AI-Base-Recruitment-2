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
  ProjectOutlined,
  SearchOutlined,
  BellOutlined,
  PlusOutlined,
  LogoutOutlined,
  UserSwitchOutlined,
  AuditOutlined,
  FileAddOutlined,
  StarOutlined,
  CommentOutlined,
  SafetyCertificateOutlined,
  LockOutlined,
} from '@ant-design/icons';
import { useAuth } from '../../context/AuthContext';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { getNotifications, markAllRead as markAllNotificationsRead } from '../../api/notifications';
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
  { key: '/pipeline', icon: <ProjectOutlined />, label: 'Pipeline' },
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

function notifIcon(type: string): React.ReactNode {
  if (type === 'new_application') return <FileAddOutlined style={{ color: '#5b6af5', fontSize: 15 }} />;
  if (type === 'stage_change') return <ProjectOutlined style={{ color: '#fbbf24', fontSize: 15 }} />;
  if (type === 'rating_update') return <StarOutlined style={{ color: '#34d399', fontSize: 15 }} />;
  if (type === 'mention') return <CommentOutlined style={{ color: '#a855f7', fontSize: 15 }} />;
  if (type === 'role_changed') return <SafetyCertificateOutlined style={{ color: '#f97316', fontSize: 15 }} />;
  if (type === 'account_status_changed') return <LockOutlined style={{ color: '#f87171', fontSize: 15 }} />;
  if (type === 'interview_scheduled' || type === 'interview_reminder') return <ProjectOutlined style={{ color: '#34d399', fontSize: 15 }} />;
  return <BellOutlined style={{ color: '#a1a1bb', fontSize: 15 }} />;
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

  const handleNotifClick = (item: Notification) => {
    const target = notifNavTarget(item);
    if (target) {
      setNotifOpen(false);
      navigate(target);
    }
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
    <div className="notification-panel">
      <List
        size="small"
        dataSource={notifications}
        locale={{ emptyText: 'No notifications' }}
        renderItem={(item) => {
          const target = notifNavTarget(item);
          return (
            <List.Item
              className={`notification-item${item.read_at ? '' : ' is-unread'}`}
              onClick={() => handleNotifClick(item)}
              style={{ cursor: target ? 'pointer' : 'default' }}
            >
              <List.Item.Meta
                avatar={<span style={{ display: 'flex', alignItems: 'center', paddingTop: 2 }}>{notifIcon(item.type)}</span>}
                title={
                  <span style={{ fontSize: 13, fontWeight: item.read_at ? 500 : 800 }}>
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
          );
        }}
      />
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
          onClick={() => { setNotifOpen(false); navigate('/notifications'); }}
          style={{ color: '#5b6af5', fontSize: 12 }}
        >
          View all notifications
        </Button>
      </div>
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
                onClick={() => navigate('/jobs', { state: { openCreate: true } })}
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
