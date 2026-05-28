import React, { useState } from 'react';
import { classifyApi, ClassifyResponse } from '../services/api';
import { ScoreBadge, CategoryChip, Spinner } from '../components/ui';
import Layout from '../components/Layout';

const EXAMPLES = [
  'Study terminated due to insufficient enrollment at trial sites',
  'Sponsor decided to discontinue the program for business reasons',
  'Interim analysis showed lack of efficacy at pre-specified futility boundary',
  'Drug-related adverse events including serious hepatotoxicity led to termination',
  'Primary endpoint of reduction in hospitalization was not met',
  'Manufacturing supply issues prevented continuation of the trial',
];

export default function ClassifyPage() {
  const [input, setInput] = useState('');
  const [result, setResult] = useState<ClassifyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleClassify = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await classifyApi.classify(input);
      setResult(res);
    } catch {
      setError('Classification failed. Make sure the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="animate-fade-in max-w-3xl mx-auto">
        <div className="mb-8">
          <h1
            className="text-3xl font-bold mb-1"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}
          >
            Failure Classifier
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Paste a clinical trial termination reason to classify the failure type, score salvageability, and generate rescue recommendations.
          </p>
        </div>

        {/* Input */}
        <div className="card p-5 mb-4">
          <label
            className="block text-xs font-medium uppercase tracking-widest mb-2"
            style={{ color: 'var(--text-muted)' }}
          >
            Termination Reason
          </label>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. The study was terminated due to lack of efficacy at interim analysis..."
            rows={5}
            className="w-full px-3 py-2.5 rounded-lg text-sm resize-none"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-primary)',
              color: 'var(--text-primary)',
              outline: 'none',
              fontFamily: 'var(--font-body)',
              lineHeight: 1.6,
            }}
            onFocus={(e) => { e.target.style.borderColor = 'rgba(0,212,255,0.4)'; }}
            onBlur={(e) => { e.target.style.borderColor = 'var(--border-primary)'; }}
          />
          <div className="flex items-center justify-between mt-3">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {input.length} chars
            </span>
            <button
              onClick={handleClassify}
              disabled={loading || !input.trim()}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-all"
              style={{
                background: input.trim() ? 'var(--accent-cyan)' : 'var(--bg-tertiary)',
                color: input.trim() ? '#0a0f14' : 'var(--text-muted)',
                border: 'none',
                cursor: input.trim() ? 'pointer' : 'not-allowed',
                fontFamily: 'var(--font-body)',
              }}
            >
              {loading && <Spinner size={14} />}
              {loading ? 'Classifying...' : 'Classify →'}
            </button>
          </div>
        </div>

        {/* Example phrases */}
        <div className="mb-8">
          <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
            Try an example:
          </p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex, i) => (
              <button
                key={i}
                onClick={() => setInput(ex)}
                className="text-xs px-2.5 py-1 rounded-full transition-all"
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-primary)',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-body)',
                  maxWidth: '240px',
                  textAlign: 'left',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {ex.length > 45 ? ex.slice(0, 45) + '…' : ex}
              </button>
            ))}
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
          <div className="animate-fade-in flex flex-col gap-4">
            {/* Classification Summary */}
            <div className="card p-5">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-4"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
              >
                Classification Result
              </h2>
              <div className="flex items-center justify-between mb-4">
                <div className="flex flex-col gap-2">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Failure Category</span>
                  <CategoryChip category={result.failure_category} />
                </div>
                <div className="flex flex-col gap-2 items-end">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Salvageability Score</span>
                  <ScoreBadge score={result.salvageability_score} size="lg" />
                </div>
              </div>
              <div
                className="p-3 rounded-lg text-sm italic"
                style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-secondary)',
                }}
              >
                "{result.why_stopped}"
              </div>
            </div>

            {/* Recommendations */}
            <div className="card p-5">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-3"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
              >
                Rescue Recommendations
              </h2>
              <div className="flex flex-col gap-2">
                {result.recommended_actions.map((rec, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 rounded-lg"
                    style={{
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    <span
                      className="text-xs font-mono font-bold mt-0.5 flex-shrink-0"
                      style={{ color: 'var(--accent-green)' }}
                    >
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{rec}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
