import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie,
} from 'recharts';
import { trialsApi, DashboardStats, Trial } from '../services/api';
import { ScoreBadge, CategoryChip, StatusChip, Skeleton } from '../components/ui';
import Layout from '../components/Layout';

const CATEGORY_PALETTE = [
  '#00d4ff', '#00e5a0', '#ffb020', '#ff4d6a', '#a78bfa', '#fb923c', '#64748b',
];

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <div
      className="card p-5 flex flex-col gap-1"
      style={{ borderColor: accent ? `${accent}30` : undefined }}
    >
      <span className="text-xs font-medium uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      <span
        className="text-3xl font-display font-bold"
        style={{ fontFamily: 'var(--font-display)', color: accent || 'var(--text-primary)' }}
      >
        {value}
      </span>
      {sub && <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{sub}</span>}
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    trialsApi
      .getStats()
      .then(setStats)
      .catch(() => setError('Failed to load dashboard stats. Make sure the backend is running.'))
      .finally(() => setLoading(false));
  }, []);

  const categoryData = stats
    ? Object.entries(stats.by_failure_category)
        .filter(([k]) => k)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value)
    : [];

  const statusData = stats
    ? Object.entries(stats.by_status)
        .filter(([k]) => k)
        .map(([name, value]) => ({ name, value }))
    : [];

  return (
    <Layout>
      <div className="animate-fade-in max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1
            className="text-3xl font-bold mb-1"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}
          >
            Intelligence Overview
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
            Terminated, withdrawn, and suspended clinical trial assets — classified and scored for rescue potential.
          </p>
        </div>

        {error && (
          <div
            className="mb-6 px-4 py-3 rounded-lg text-sm"
            style={{
              background: 'rgba(255,77,106,0.1)',
              border: '1px solid rgba(255,77,106,0.3)',
              color: '#ff4d6a',
            }}
          >
            ⚠ {error}
          </div>
        )}

        {/* Stat Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))
          ) : (
            <>
              <StatCard
                label="Total Failed Trials"
                value={stats?.total_trials ?? 0}
                sub="In database"
                accent="var(--accent-cyan)"
              />
              <StatCard
                label="Avg Salvageability"
                value={`${stats?.avg_salvageability ?? 0}`}
                sub="Out of 100"
                accent="var(--accent-green)"
              />
              <StatCard
                label="Terminated"
                value={stats?.by_status?.['TERMINATED'] ?? 0}
                sub="Hard stop"
                accent="var(--accent-red)"
              />
              <StatCard
                label="Withdrawn"
                value={stats?.by_status?.['WITHDRAWN'] ?? 0}
                sub="Sponsor withdrawal"
                accent="var(--accent-amber)"
              />
            </>
          )}
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Failure Category Bar Chart */}
          <div className="card p-5">
            <h2
              className="text-sm font-semibold mb-4 uppercase tracking-widest"
              style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
            >
              Failure Distribution
            </h2>
            {loading ? (
              <Skeleton className="h-48" />
            ) : categoryData.length === 0 ? (
              <div className="h-48 flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>
                No data yet — run an ingest first
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={categoryData} layout="vertical" barSize={12}>
                  <XAxis type="number" tick={{ fill: '#4a5568', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={140}
                    tick={{ fill: '#8b98a8', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-primary)',
                      borderRadius: '8px',
                      color: 'var(--text-primary)',
                      fontSize: '12px',
                    }}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {categoryData.map((_, index) => (
                      <Cell key={index} fill={CATEGORY_PALETTE[index % CATEGORY_PALETTE.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Status Pie Chart */}
          <div className="card p-5">
            <h2
              className="text-sm font-semibold mb-4 uppercase tracking-widest"
              style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
            >
              Status Breakdown
            </h2>
            {loading ? (
              <Skeleton className="h-48" />
            ) : statusData.length === 0 ? (
              <div className="h-48 flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>
                No data yet — run an ingest first
              </div>
            ) : (
              <div className="flex items-center gap-6">
                <ResponsiveContainer width="50%" height={160}>
                  <PieChart>
                    <Pie
                      data={statusData}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={70}
                      dataKey="value"
                      strokeWidth={0}
                    >
                      {statusData.map((_, i) => (
                        <Cell key={i} fill={['#ff4d6a', '#ffb020', '#a78bfa'][i % 3]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-primary)',
                        borderRadius: '8px',
                        color: 'var(--text-primary)',
                        fontSize: '12px',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-col gap-2">
                  {statusData.map((d, i) => (
                    <div key={d.name} className="flex items-center gap-2 text-xs">
                      <div
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ background: ['#ff4d6a', '#ffb020', '#a78bfa'][i % 3] }}
                      />
                      <span style={{ color: 'var(--text-secondary)' }}>{d.name}</span>
                      <span className="font-mono ml-auto" style={{ color: 'var(--text-primary)' }}>
                        {d.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Top Salvageable */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2
              className="text-sm font-semibold uppercase tracking-widest"
              style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
            >
              Top Salvageable Assets
            </h2>
            <Link
              href="/trials?min_score=70"
              className="text-xs"
              style={{ color: 'var(--accent-cyan)', textDecoration: 'none' }}
            >
              View all →
            </Link>
          </div>
          {loading ? (
            <div className="flex flex-col gap-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : (stats?.top_salvageable ?? []).length === 0 ? (
            <div className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
              No trials yet.{' '}
              <Link href="/ingest" style={{ color: 'var(--accent-cyan)' }}>
                Run an ingest
              </Link>{' '}
              to populate data.
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {(stats?.top_salvageable ?? []).map((trial: Trial) => (
                <Link
                  key={trial.id}
                  href={`/trials/${trial.id}`}
                  className="flex items-center gap-4 p-3 rounded-lg transition-all"
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-subtle)',
                    textDecoration: 'none',
                  }}
                >
                  <ScoreBadge score={trial.salvageability_score} />
                  <div className="flex-1 min-w-0">
                    <div
                      className="text-sm font-medium truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {trial.title || trial.nct_id}
                    </div>
                    <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {trial.drug_name || '—'} · {trial.condition || '—'}
                    </div>
                  </div>
                  <CategoryChip category={trial.failure_category} size="sm" />
                  <StatusChip status={trial.overall_status} />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
