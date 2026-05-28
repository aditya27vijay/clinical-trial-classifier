import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { trialsApi, Trial } from '../../services/api';
import { ScoreBadge, CategoryChip, StatusChip, PhaseBadge, Spinner } from '../../components/ui';
import Layout from '../../components/Layout';

function InfoRow({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="flex flex-col gap-0.5 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
      <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      <span className="text-sm" style={{ color: value ? 'var(--text-primary)' : 'var(--text-muted)' }}>
        {value ?? '—'}
      </span>
    </div>
  );
}

function ScoreGauge({ score }: { score?: number | null }) {
  const s = score ?? 0;
  const color = s >= 70 ? 'var(--accent-green)' : s >= 45 ? 'var(--accent-amber)' : 'var(--accent-red)';
  const label = s >= 70 ? 'High Salvageability' : s >= 45 ? 'Medium Salvageability' : 'Low Salvageability';

  const circumference = 2 * Math.PI * 54;
  const strokeDash = (s / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-2 py-4">
      <div className="relative" style={{ width: 130, height: 130 }}>
        <svg viewBox="0 0 130 130" className="rotate-[-90deg]">
          <circle cx="65" cy="65" r="54" fill="none" stroke="var(--bg-tertiary)" strokeWidth="10" />
          <circle
            cx="65" cy="65" r="54" fill="none"
            stroke={color} strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${strokeDash} ${circumference}`}
            style={{ transition: 'stroke-dasharray 1s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold font-mono" style={{ color }}>{s}</span>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>/100</span>
        </div>
      </div>
      <span className="text-sm font-medium" style={{ color }}>{label}</span>
    </div>
  );
}

export default function TrialDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [trial, setTrial] = useState<Trial | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    trialsApi
      .getById(Number(id))
      .then(setTrial)
      .catch(() => setError('Trial not found.'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-64">
          <Spinner size={32} />
        </div>
      </Layout>
    );
  }

  if (error || !trial) {
    return (
      <Layout>
        <div className="text-center py-16">
          <p className="text-sm mb-4" style={{ color: 'var(--accent-red)' }}>{error || 'Trial not found'}</p>
          <Link href="/trials" style={{ color: 'var(--accent-cyan)', fontSize: '14px' }}>
            ← Back to trials
          </Link>
        </div>
      </Layout>
    );
  }

  const recommendations: string[] = Array.isArray(trial.recommended_actions)
    ? trial.recommended_actions
    : [];

  return (
    <Layout>
      <div className="animate-fade-in max-w-5xl mx-auto">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-xs mb-6" style={{ color: 'var(--text-muted)' }}>
          <Link href="/trials" style={{ color: 'var(--accent-cyan)', textDecoration: 'none' }}>
            ← All Trials
          </Link>
          <span>/</span>
          <span className="font-mono">{trial.nct_id}</span>
        </div>

        {/* Title Row */}
        <div className="mb-6">
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <StatusChip status={trial.overall_status} />
            <PhaseBadge phase={trial.phase} />
            <CategoryChip category={trial.failure_category} />
          </div>
          <h1
            className="text-2xl font-bold leading-tight mb-1"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}
          >
            {trial.title || 'Untitled Trial'}
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {trial.drug_name && <><span style={{ color: 'var(--accent-cyan)' }}>{trial.drug_name}</span> · </>}
            {trial.condition}
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Metadata */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            {/* Why Stopped */}
            <div className="card p-5">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-3"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
              >
                Termination Reason
              </h2>
              <p
                className="text-sm leading-relaxed p-3 rounded-lg"
                style={{
                  color: 'var(--text-primary)',
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-primary)',
                  fontStyle: trial.why_stopped ? 'normal' : 'italic',
                }}
              >
                {trial.why_stopped || 'No termination reason provided.'}
              </p>
            </div>

            {/* Recommendations */}
            <div className="card p-5">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-3"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
              >
                Rescue Recommendations
              </h2>
              {recommendations.length === 0 ? (
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No recommendations available.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {recommendations.map((rec, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-3 p-3 rounded-lg"
                      style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)' }}
                    >
                      <span
                        className="text-xs font-mono font-bold mt-0.5 flex-shrink-0"
                        style={{ color: 'var(--accent-cyan)' }}
                      >
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{rec}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Trial Metadata */}
            <div className="card p-5">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-3"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
              >
                Trial Metadata
              </h2>
              <InfoRow label="NCT ID" value={trial.nct_id} />
              <InfoRow label="Sponsor" value={trial.sponsor} />
              <InfoRow label="Condition / Disease" value={trial.condition} />
              <InfoRow label="Drug / Intervention" value={trial.drug_name} />
              <InfoRow label="Phase" value={trial.phase} />
              <InfoRow label="Enrollment" value={trial.enrollment ? `${trial.enrollment.toLocaleString()} patients` : undefined} />
              <InfoRow label="Start Date" value={trial.start_date} />
              <InfoRow label="Completion Date" value={trial.completion_date} />
              <InfoRow label="Ingested At" value={trial.created_at ? new Date(trial.created_at).toLocaleString() : undefined} />
            </div>
          </div>

          {/* Right: Score + Links */}
          <div className="flex flex-col gap-6">
            {/* Salvageability Score */}
            <div className="card p-5">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-2"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
              >
                Salvageability Score
              </h2>
              <ScoreGauge score={trial.salvageability_score} />
              <div
                className="text-xs text-center mt-2 p-2 rounded-lg"
                style={{ background: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}
              >
                Rule-based score based on failure category and contextual signals
              </div>
            </div>

            {/* External Links */}
            <div className="card p-5">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-3"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
              >
                External Resources
              </h2>
              <div className="flex flex-col gap-2">
                <a
                  href={`https://clinicaltrials.gov/study/${trial.nct_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm transition-all"
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-primary)',
                    color: 'var(--accent-cyan)',
                    textDecoration: 'none',
                  }}
                >
                  <span>↗</span> View on ClinicalTrials.gov
                </a>
                <a
                  href={`https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(trial.nct_id)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm transition-all"
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-primary)',
                    color: 'var(--text-secondary)',
                    textDecoration: 'none',
                  }}
                >
                  <span>↗</span> Search PubMed
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
