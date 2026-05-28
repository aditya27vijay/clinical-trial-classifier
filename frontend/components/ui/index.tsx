import React from 'react';
import clsx from 'clsx';

// ─── Score Badge ──────────────────────────────────────────────────────────────

interface ScoreBadgeProps {
  score?: number | null;
  size?: 'sm' | 'md' | 'lg';
}

export function ScoreBadge({ score, size = 'md' }: ScoreBadgeProps) {
  if (score === undefined || score === null) {
    return <span className="text-[var(--text-muted)] font-mono text-xs">N/A</span>;
  }

  const color =
    score >= 70
      ? 'var(--accent-green)'
      : score >= 45
      ? 'var(--accent-amber)'
      : 'var(--accent-red)';

  const bg =
    score >= 70
      ? 'rgba(0,229,160,0.1)'
      : score >= 45
      ? 'rgba(255,176,32,0.1)'
      : 'rgba(255,77,106,0.1)';

  const sizes = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={clsx('font-mono font-medium rounded-md border inline-flex items-center gap-1', sizes[size])}
      style={{ color, background: bg, borderColor: color + '40' }}
    >
      {score}
    </span>
  );
}

// ─── Failure Category Chip ────────────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, { text: string; bg: string; border: string }> = {
  'Lack of efficacy': { text: '#ff4d6a', bg: 'rgba(255,77,106,0.1)', border: 'rgba(255,77,106,0.3)' },
  'Toxicity': { text: '#ff7043', bg: 'rgba(255,112,67,0.1)', border: 'rgba(255,112,67,0.3)' },
  'Recruitment failure': { text: '#ffb020', bg: 'rgba(255,176,32,0.1)', border: 'rgba(255,176,32,0.3)' },
  'Business termination': { text: '#00d4ff', bg: 'rgba(0,212,255,0.1)', border: 'rgba(0,212,255,0.3)' },
  'Operational issue': { text: '#a78bfa', bg: 'rgba(167,139,250,0.1)', border: 'rgba(167,139,250,0.3)' },
  'Endpoint failure': { text: '#fb923c', bg: 'rgba(251,146,60,0.1)', border: 'rgba(251,146,60,0.3)' },
  'Unknown': { text: '#8b98a8', bg: 'rgba(139,152,168,0.1)', border: 'rgba(139,152,168,0.3)' },
};

interface CategoryChipProps {
  category?: string | null;
  size?: 'sm' | 'md';
}

export function CategoryChip({ category, size = 'md' }: CategoryChipProps) {
  const cat = category || 'Unknown';
  const colors = CATEGORY_COLORS[cat] || CATEGORY_COLORS['Unknown'];

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full font-medium',
        size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1'
      )}
      style={{ color: colors.text, background: colors.bg, border: `1px solid ${colors.border}` }}
    >
      {cat}
    </span>
  );
}

// ─── Status Chip ──────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, { text: string; bg: string }> = {
  TERMINATED: { text: '#ff4d6a', bg: 'rgba(255,77,106,0.1)' },
  WITHDRAWN: { text: '#ffb020', bg: 'rgba(255,176,32,0.1)' },
  SUSPENDED: { text: '#a78bfa', bg: 'rgba(167,139,250,0.1)' },
};

export function StatusChip({ status }: { status?: string | null }) {
  const s = status?.toUpperCase() || 'UNKNOWN';
  const colors = STATUS_COLORS[s] || { text: '#8b98a8', bg: 'rgba(139,152,168,0.1)' };
  return (
    <span
      className="text-xs font-mono font-medium px-2 py-0.5 rounded"
      style={{ color: colors.text, background: colors.bg }}
    >
      {s}
    </span>
  );
}

// ─── Loading Spinner ──────────────────────────────────────────────────────────

export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className="animate-spin-slow"
      style={{ animation: 'spin 0.8s linear infinite' }}
    >
      <circle cx="12" cy="12" r="10" stroke="var(--border-primary)" strokeWidth="2" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="var(--accent-cyan)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton', className)} />;
}

// ─── Empty State ──────────────────────────────────────────────────────────────

export function EmptyState({ message = 'No data found' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <div className="w-12 h-12 rounded-full border border-[var(--border-primary)] flex items-center justify-center">
        <span className="text-2xl">🔬</span>
      </div>
      <p className="text-[var(--text-muted)] text-sm">{message}</p>
    </div>
  );
}

// ─── Phase Badge ──────────────────────────────────────────────────────────────

export function PhaseBadge({ phase }: { phase?: string | null }) {
  if (!phase) return <span className="text-[var(--text-muted)] text-xs">—</span>;
  return (
    <span
      className="text-xs font-mono px-2 py-0.5 rounded border"
      style={{
        color: 'var(--accent-cyan)',
        background: 'rgba(0,212,255,0.08)',
        borderColor: 'rgba(0,212,255,0.2)',
      }}
    >
      {phase}
    </span>
  );
}
