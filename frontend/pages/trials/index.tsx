import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { trialsApi, Trial, TrialListResponse } from '../../services/api';
import { ScoreBadge, CategoryChip, StatusChip, PhaseBadge, Spinner, EmptyState } from '../../components/ui';
import Layout from '../../components/Layout';

const CATEGORIES = [
  '', 'Lack of efficacy', 'Toxicity', 'Recruitment failure',
  'Business termination', 'Operational issue', 'Endpoint failure', 'Unknown',
];
const PHASES = ['', 'PHASE1', 'PHASE2', 'PHASE3', 'PHASE4', 'EARLY_PHASE1', 'NA'];
const STATUSES = ['', 'TERMINATED', 'WITHDRAWN', 'SUSPENDED'];

export default function TrialsPage() {
  const router = useRouter();
  const [data, setData] = useState<TrialListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [phase, setPhase] = useState('');
  const [failureCategory, setFailureCategory] = useState('');
  const [status, setStatus] = useState('');
  const [minScore, setMinScore] = useState('');
  const [page, setPage] = useState(1);

  // Sync from URL on first load
  useEffect(() => {
    if (router.query.min_score) setMinScore(router.query.min_score as string);
  }, [router.query]);

  const fetchTrials = useCallback(async () => {
    setLoading(true);
    try {
      const result = await trialsApi.list({
        page,
        page_size: 25,
        search: search || undefined,
        phase: phase || undefined,
        failure_category: failureCategory || undefined,
        overall_status: status || undefined,
        min_score: minScore ? parseInt(minScore) : undefined,
      });
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, search, phase, failureCategory, status, minScore]);

  useEffect(() => {
    const timer = setTimeout(fetchTrials, 300);
    return () => clearTimeout(timer);
  }, [fetchTrials]);

  // Reset page on filter change
  useEffect(() => { setPage(1); }, [search, phase, failureCategory, status, minScore]);

  const totalPages = data ? Math.ceil(data.total / 25) : 0;

  return (
    <Layout>
      <div className="animate-fade-in max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1
            className="text-3xl font-bold mb-1"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}
          >
            Failed Trials
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {data?.total ?? '—'} trials · Sorted by salvageability score
          </p>
        </div>

        {/* Filters */}
        <div
          className="rounded-xl p-4 mb-6 flex flex-wrap gap-3"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)' }}
        >
          <input
            type="text"
            placeholder="Search drug, disease, sponsor, NCT ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-[200px] px-3 py-2 rounded-lg text-sm"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-primary)',
              color: 'var(--text-primary)',
              outline: 'none',
              fontFamily: 'var(--font-body)',
            }}
          />
          <select
            value={failureCategory}
            onChange={(e) => setFailureCategory(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-primary)',
              color: failureCategory ? 'var(--text-primary)' : 'var(--text-muted)',
              outline: 'none',
            }}
          >
            <option value="">All categories</option>
            {CATEGORIES.filter(Boolean).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <select
            value={phase}
            onChange={(e) => setPhase(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-primary)',
              color: phase ? 'var(--text-primary)' : 'var(--text-muted)',
              outline: 'none',
            }}
          >
            <option value="">All phases</option>
            {PHASES.filter(Boolean).map((p) => (
              <option key={p} value={p}>{p.replace('_', ' ')}</option>
            ))}
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-primary)',
              color: status ? 'var(--text-primary)' : 'var(--text-muted)',
              outline: 'none',
            }}
          >
            <option value="">All statuses</option>
            {STATUSES.filter(Boolean).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input
            type="number"
            placeholder="Min score"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            min={0} max={100}
            className="w-24 px-3 py-2 rounded-lg text-sm"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-primary)',
              color: 'var(--text-primary)',
              outline: 'none',
            }}
          />
        </div>

        {/* Table */}
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: '1px solid var(--border-primary)' }}
        >
          {/* Table Header */}
          <div
            className="grid text-xs font-medium uppercase tracking-widest px-4 py-3"
            style={{
              background: 'var(--bg-secondary)',
              color: 'var(--text-muted)',
              gridTemplateColumns: '80px 1fr 140px 100px 120px 90px 90px',
              borderBottom: '1px solid var(--border-primary)',
            }}
          >
            <span>Score</span>
            <span>Trial / Drug</span>
            <span>Condition</span>
            <span>Phase</span>
            <span>Failure Type</span>
            <span>Status</span>
            <span>NCT ID</span>
          </div>

          {/* Rows */}
          <div style={{ background: 'var(--bg-card)' }}>
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Spinner size={24} />
              </div>
            ) : !data || data.results.length === 0 ? (
              <EmptyState message="No trials match your filters. Try adjusting search or run an ingest." />
            ) : (
              data.results.map((trial: Trial, i) => (
                <Link
                  key={trial.id}
                  href={`/trials/${trial.id}`}
                  className="grid items-center px-4 py-3 transition-all"
                  style={{
                    gridTemplateColumns: '80px 1fr 140px 100px 120px 90px 90px',
                    borderBottom: i < data.results.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                    textDecoration: 'none',
                    color: 'inherit',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }}
                >
                  <ScoreBadge score={trial.salvageability_score} size="sm" />
                  <div className="min-w-0 pr-4">
                    <div
                      className="text-sm font-medium truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {trial.title || 'Untitled Trial'}
                    </div>
                    <div className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                      {trial.drug_name || '—'}
                    </div>
                  </div>
                  <div
                    className="text-xs truncate pr-2"
                    style={{ color: 'var(--text-secondary)' }}
                    title={trial.condition || ''}
                  >
                    {trial.condition || '—'}
                  </div>
                  <PhaseBadge phase={trial.phase} />
                  <CategoryChip category={trial.failure_category} size="sm" />
                  <StatusChip status={trial.overall_status} />
                  <span
                    className="text-xs font-mono"
                    style={{ color: 'var(--accent-cyan)' }}
                  >
                    {trial.nct_id}
                  </span>
                </Link>
              ))
            )}
          </div>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Page {page} of {totalPages} · {data?.total} total
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-lg text-xs transition-all"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-primary)',
                  color: page === 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                  cursor: page === 1 ? 'not-allowed' : 'pointer',
                }}
              >
                ← Prev
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const p = Math.max(1, Math.min(page - 2, totalPages - 4)) + i;
                return (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className="w-8 h-8 rounded-lg text-xs transition-all"
                    style={{
                      background: p === page ? 'var(--accent-cyan-dim)' : 'var(--bg-secondary)',
                      border: `1px solid ${p === page ? 'rgba(0,212,255,0.4)' : 'var(--border-primary)'}`,
                      color: p === page ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                      cursor: 'pointer',
                    }}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg text-xs transition-all"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-primary)',
                  color: page === totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                  cursor: page === totalPages ? 'not-allowed' : 'pointer',
                }}
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
