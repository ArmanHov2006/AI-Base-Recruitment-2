import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  TeamOutlined,
  FileTextOutlined,
  BarChartOutlined,
  UserSwitchOutlined,
  AuditOutlined,
  SearchOutlined,
  UserOutlined,
  EnterOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';
import { searchCandidates } from '../api/candidates';
import { listJobs } from '../api/jobs';

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  isAdmin: boolean;
}

interface CommandItem {
  id: string;
  group: 'Navigate' | 'Candidates' | 'Jobs';
  label: string;
  sub?: string;
  icon: ReactNode;
  run: () => void;
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export default function CommandPalette({ open, onClose, isAdmin }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debouncedQuery = useDebounced(query.trim(), 200);

  // Reset on every open so it always starts clean and focused.
  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
      // focus after paint
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  const jobsQuery = useQuery({
    queryKey: ['cmdk', 'jobs'],
    queryFn: listJobs,
    enabled: open,
    staleTime: 60_000,
  });

  const candidatesQuery = useQuery({
    queryKey: ['cmdk', 'candidates', debouncedQuery],
    queryFn: () => searchCandidates({ q: debouncedQuery, size: 6 }),
    enabled: open && debouncedQuery.length > 0,
    staleTime: 30_000,
  });

  const go = (path: string) => {
    onClose();
    navigate(path);
  };

  const items = useMemo<CommandItem[]>(() => {
    const q = debouncedQuery.toLowerCase();

    const navAll: CommandItem[] = [
      { id: 'nav-candidates', group: 'Navigate', label: 'Candidates', icon: <TeamOutlined />, run: () => go('/') },
      { id: 'nav-jobs', group: 'Navigate', label: 'Jobs', icon: <FileTextOutlined />, run: () => go('/jobs') },
      { id: 'nav-analytics', group: 'Navigate', label: 'Analytics', icon: <BarChartOutlined />, run: () => go('/analytics') },
      ...(isAdmin
        ? [
            { id: 'nav-users', group: 'Navigate' as const, label: 'User Management', icon: <UserSwitchOutlined />, run: () => go('/admin/users') },
            { id: 'nav-audit', group: 'Navigate' as const, label: 'Audit Log', icon: <AuditOutlined />, run: () => go('/admin/audit') },
          ]
        : []),
    ];
    const nav = q ? navAll.filter((i) => i.label.toLowerCase().includes(q)) : navAll;

    const candidates: CommandItem[] = (candidatesQuery.data?.items ?? []).map((c) => ({
      id: `cand-${c.id}`,
      group: 'Candidates',
      label: c.name || c.email || 'Unnamed candidate',
      sub: [c.desired_position, c.seniority].filter(Boolean).join(' · ') || c.email || undefined,
      icon: <UserOutlined />,
      run: () => go(`/candidates/${c.id}`),
    }));

    const jobs: CommandItem[] = (jobsQuery.data ?? [])
      .filter((j) => (q ? j.title.toLowerCase().includes(q) : true))
      .slice(0, 6)
      .map((j) => ({
        id: `job-${j.id}`,
        group: 'Jobs',
        label: j.title,
        sub: [j.required_seniority, j.location].filter(Boolean).join(' · ') || undefined,
        icon: <FileTextOutlined />,
        run: () => go(`/jobs/${j.id}`),
      }));

    return [...nav, ...candidates, ...jobs];
  }, [debouncedQuery, candidatesQuery.data, jobsQuery.data, isAdmin]);

  // Clamp active index when the result set shrinks.
  useEffect(() => {
    setActive((a) => (a >= items.length ? Math.max(0, items.length - 1) : a));
  }, [items.length]);

  // Keep the active row scrolled into view.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => (items.length ? (a + 1) % items.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => (items.length ? (a - 1 + items.length) % items.length : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      items[active]?.run();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  // Render with group headers, tracking a flat index for keyboard nav.
  let flatIdx = -1;
  const groups: CommandItem['group'][] = ['Navigate', 'Candidates', 'Jobs'];

  return (
    <div
      className="cmdk-overlay"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="cmdk-panel" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="cmdk-input-row">
          <SearchOutlined className="cmdk-input-icon" />
          <input
            ref={inputRef}
            className="cmdk-input"
            placeholder="Search candidates, jobs, or jump to a page…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label="Command palette search"
          />
          <span className="cmdk-esc">ESC</span>
        </div>

        <div className="cmdk-list" ref={listRef}>
          {items.length === 0 ? (
            <div className="cmdk-empty">
              {debouncedQuery ? 'No matches' : 'Type to search'}
            </div>
          ) : (
            groups.map((group) => {
              const groupItems = items.filter((i) => i.group === group);
              if (groupItems.length === 0) return null;
              return (
                <div key={group} className="cmdk-group">
                  <div className="cmdk-group-label">{group}</div>
                  {groupItems.map((item) => {
                    flatIdx += 1;
                    const idx = flatIdx;
                    return (
                      <button
                        type="button"
                        key={item.id}
                        data-idx={idx}
                        className={`cmdk-item${idx === active ? ' is-active' : ''}`}
                        onMouseEnter={() => setActive(idx)}
                        onClick={() => item.run()}
                      >
                        <span className="cmdk-item-icon">{item.icon}</span>
                        <span className="cmdk-item-text">
                          <span className="cmdk-item-label">{item.label}</span>
                          {item.sub && <span className="cmdk-item-sub">{item.sub}</span>}
                        </span>
                        {idx === active && <EnterOutlined className="cmdk-item-enter" />}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <div className="cmdk-footer">
          <span><span className="cmdk-kbd">↑</span><span className="cmdk-kbd">↓</span> navigate</span>
          <span><span className="cmdk-kbd">↵</span> open</span>
          <span><span className="cmdk-kbd">esc</span> close</span>
        </div>
      </div>
    </div>
  );
}
