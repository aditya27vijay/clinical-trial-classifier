import React, { useState } from 'react';
import { ingestApi, IngestResponse } from '../services/api';
import { Spinner } from '../components/ui';
import Layout from '../components/Layout';

export default function IngestPage() {
  const [maxResults, setMaxResults] = useState(100);
  const [condition, setCondition] = useState('');
  const [intervention, setIntervention] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [error, setError] = useState('');

  const handleIngest = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await ingestApi.trigger({
        max_results: maxResults,
        condition: condition || undefined,
        intervention: intervention || undefined,
      });
      setResult(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Ingestion failed. Make sure the backend and database are running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="animate-fade-in max-w-2xl mx-auto">
        <div className="mb-8">
          <h1
            className="text-3xl font-bold mb-1"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}
          >
            Ingest Data
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Fetch terminated, withdrawn, and suspended clinical trials from ClinicalTrials.gov.
            Trials are classified and scored automatically on ingestion.
          </p>
        </div>

        {/* Form */}
        <div className="card p-6 mb-6">
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-5"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
          >
            Ingestion Parameters
          </h2>

          <div className="flex flex-col gap-4">
            <div>
              <label
                className="block text-xs font-medium mb-1.5"
                style={{ color: 'var(--text-muted)' }}
              >
                Max Results
              </label>
              <input
                type="number"
                value={maxResults}
                onChange={(e) => setMaxResults(Number(e.target.value))}
                min={1} max={1000}
                className="w-full px-3 py-2.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-primary)',
                  color: 'var(--text-primary)',
                  outline: 'none',
                  fontFamily: 'var(--font-body)',
                }}
              />
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                Number of trials to fetch (1–1000). Start with 50–100 for testing.
              </p>
            </div>

            <div>
              <label
                className="block text-xs font-medium mb-1.5"
                style={{ color: 'var(--text-muted)' }}
              >
                Filter by Condition (optional)
              </label>
              <input
                type="text"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                placeholder="e.g. cancer, diabetes, alzheimer"
                className="w-full px-3 py-2.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-primary)',
                  color: 'var(--text-primary)',
                  outline: 'none',
                  fontFamily: 'var(--font-body)',
                }}
              />
            </div>

            <div>
              <label
                className="block text-xs font-medium mb-1.5"
                style={{ color: 'var(--text-muted)' }}
              >
                Filter by Intervention / Drug (optional)
              </label>
              <input
                type="text"
                value={intervention}
                onChange={(e) => setIntervention(e.target.value)}
                placeholder="e.g. pembrolizumab, metformin"
                className="w-full px-3 py-2.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-primary)',
                  color: 'var(--text-primary)',
                  outline: 'none',
                  fontFamily: 'var(--font-body)',
                }}
              />
            </div>
          </div>

          <div className="mt-6 pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <button
              onClick={handleIngest}
              disabled={loading}
              className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-medium transition-all w-full justify-center"
              style={{
                background: loading ? 'var(--bg-tertiary)' : 'var(--accent-cyan)',
                color: loading ? 'var(--text-muted)' : '#0a0f14',
                border: 'none',
                cursor: loading ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-body)',
              }}
            >
              {loading && <Spinner size={16} />}
              {loading ? `Fetching from ClinicalTrials.gov...` : '⊕ Run Ingestion'}
            </button>
            {loading && (
              <p className="text-xs text-center mt-2" style={{ color: 'var(--text-muted)' }}>
                This may take 30–90 seconds depending on volume
              </p>
            )}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div
            className="mb-4 px-4 py-3 rounded-lg text-sm"
            style={{ background: 'rgba(255,77,106,0.1)', border: '1px solid rgba(255,77,106,0.3)', color: '#ff4d6a' }}
          >
            ⚠ {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div
            className="animate-fade-in card p-5"
            style={{ borderColor: 'rgba(0,229,160,0.3)' }}
          >
            <div className="flex items-center gap-2 mb-4">
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center text-xs"
                style={{ background: 'rgba(0,229,160,0.15)', color: 'var(--accent-green)' }}
              >
                ✓
              </div>
              <h2
                className="text-sm font-semibold"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--accent-green)' }}
              >
                Ingestion Complete
              </h2>
            </div>
            <div className="grid grid-cols-3 gap-4 mb-4">
              {[
                { label: 'Fetched', value: result.fetched, color: 'var(--accent-cyan)' },
                { label: 'Inserted', value: result.inserted, color: 'var(--accent-green)' },
                { label: 'Updated', value: result.skipped, color: 'var(--accent-amber)' },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="flex flex-col items-center gap-1 p-3 rounded-lg"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <span
                    className="text-2xl font-bold font-mono"
                    style={{ color: stat.color, fontFamily: 'var(--font-mono)' }}
                  >
                    {stat.value}
                  </span>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{stat.label}</span>
                </div>
              ))}
            </div>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{result.message}</p>
          </div>
        )}

        {/* Info box */}
        <div
          className="mt-6 p-4 rounded-lg text-xs"
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-primary)',
            color: 'var(--text-muted)',
            lineHeight: 1.7,
          }}
        >
          <strong style={{ color: 'var(--text-secondary)' }}>How it works:</strong> This fetches trials with status
          TERMINATED, WITHDRAWN, or SUSPENDED from the ClinicalTrials.gov v2 API. Each trial's termination
          reason is run through the rule-based classifier to assign a failure category and salvageability score.
          Duplicate NCT IDs are updated rather than re-inserted.
        </div>
      </div>
    </Layout>
  );
}
