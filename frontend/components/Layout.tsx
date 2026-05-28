import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import clsx from 'clsx';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: '◉' },
  { href: '/trials', label: 'Trials', icon: '⊞' },
  { href: '/classify', label: 'Classifier', icon: '◈' },
  { href: '/ingest', label: 'Ingest Data', icon: '⊕' },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      {/* Sidebar */}
      <aside
        className="flex flex-col border-r transition-all duration-300"
        style={{
          width: collapsed ? '60px' : '220px',
          borderColor: 'var(--border-primary)',
          background: 'var(--bg-secondary)',
          flexShrink: 0,
        }}
      >
        {/* Logo */}
        <div
          className="flex items-center gap-3 p-4 border-b"
          style={{ borderColor: 'var(--border-primary)', height: '60px' }}
        >
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: 'var(--accent-cyan-dim)', border: '1px solid rgba(0,212,255,0.3)' }}
          >
            <span style={{ color: 'var(--accent-cyan)', fontSize: '14px' }}>⚕</span>
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div
                className="font-display font-700 text-sm leading-tight truncate"
                style={{ fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--text-primary)' }}
              >
                TrialIntel
              </div>
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                MVP v1
              </div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 p-2 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const active = router.pathname === item.href || (item.href !== '/' && router.pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 group',
                  active ? 'active-nav' : ''
                )}
                style={{
                  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                  background: active ? 'var(--accent-cyan-dim)' : 'transparent',
                  border: active ? '1px solid rgba(0,212,255,0.2)' : '1px solid transparent',
                  textDecoration: 'none',
                }}
                title={collapsed ? item.label : undefined}
              >
                <span className="text-base flex-shrink-0">{item.icon}</span>
                {!collapsed && (
                  <span
                    className="text-sm font-medium"
                    style={{ fontFamily: 'var(--font-body)' }}
                  >
                    {item.label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="m-2 p-2 rounded-lg text-xs transition-all"
          style={{
            color: 'var(--text-muted)',
            background: 'transparent',
            border: '1px solid var(--border-subtle)',
            cursor: 'pointer',
          }}
          title="Toggle sidebar"
        >
          {collapsed ? '→' : '←'}
        </button>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header
          className="flex items-center justify-between px-6 border-b"
          style={{
            height: '60px',
            borderColor: 'var(--border-primary)',
            background: 'var(--bg-secondary)',
            flexShrink: 0,
          }}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Clinical Trial Failure Intelligence System
            </span>
            <span style={{ color: 'var(--border-primary)' }}>/</span>
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--text-secondary)' }}
            >
              {NAV_ITEMS.find(n => n.href === router.pathname || (n.href !== '/' && router.pathname.startsWith(n.href)))?.label || 'Dashboard'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="h-2 w-2 rounded-full"
              style={{ background: 'var(--accent-green)', boxShadow: '0 0 6px var(--accent-green)' }}
            />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              API Connected
            </span>
          </div>
        </header>

        <div className="flex-1 overflow-auto p-6">
          {children}
        </div>
      </main>
    </div>
  );
}
