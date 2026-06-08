import { useState, useEffect } from "react";
import Layout from "../../components/Layout";
import Link from "next/link";
import axios from "axios";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const MODALITIES = ["small_molecule","biologic_antibody","gene_therapy","cell_therapy","rna_therapy","vaccine","device_procedure"];
const MODALITY_COLORS: Record<string, string> = {
  small_molecule:    "bg-blue-500/20 text-blue-300 border-blue-500/30",
  biologic_antibody: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  gene_therapy:      "bg-green-500/20 text-green-300 border-green-500/30",
  cell_therapy:      "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
  rna_therapy:       "bg-pink-500/20 text-pink-300 border-pink-500/30",
  vaccine:           "bg-orange-500/20 text-orange-300 border-orange-500/30",
  device_procedure:  "bg-gray-500/20 text-gray-300 border-gray-500/30",
};
const IP_COLORS: Record<string, string> = {
  expired: "bg-green-500/20 text-green-300",
  active:  "bg-red-500/20 text-red-300",
  unknown: "bg-gray-500/20 text-gray-400",
};

function ScoreBar({ score }: { score: number }) {
  const color = score >= 70 ? "#22c55e" : score >= 45 ? "#f59e0b" : "#ef4444";
  return (
    <div className="space-y-1">
      <span className="text-lg font-bold" style={{ color }}>{score}</span>
      <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${score}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function MoleculeCard({ mol }: { mol: any }) {
  const modStyle = MODALITY_COLORS[mol.modality] || "bg-gray-500/20 text-gray-300 border-gray-500/30";
  const ipStyle  = IP_COLORS[mol.ip_status || "unknown"];
  return (
    <Link href={`/molecules/${mol.id}`}>
      <div className="bg-white/5 border border-white/10 rounded-xl p-5 hover:bg-white/8 hover:border-white/20 transition-all cursor-pointer h-full flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h3 className="text-white font-semibold text-sm leading-tight truncate">{mol.canonical_name}</h3>
            {mol.inn_name && mol.inn_name !== mol.canonical_name && (
              <p className="text-gray-400 text-xs mt-0.5">{mol.inn_name}</p>
            )}
          </div>
          {mol.modality && (
            <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${modStyle}`}>
              {mol.modality.replace("_", " ")}
            </span>
          )}
        </div>
        {mol.mechanism_of_action && (
          <p className="text-gray-400 text-xs leading-relaxed line-clamp-2">{mol.mechanism_of_action}</p>
        )}
        {mol.primary_targets?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {mol.primary_targets.slice(0, 3).map((t: string) => (
              <span key={t} className="text-xs bg-white/5 border border-white/10 px-2 py-0.5 rounded text-gray-300">{t}</span>
            ))}
            {mol.primary_targets.length > 3 && <span className="text-xs text-gray-500">+{mol.primary_targets.length - 3}</span>}
          </div>
        )}
        {mol.best_salvageability != null && <ScoreBar score={mol.best_salvageability} />}
        <div className="flex items-center justify-between pt-1 border-t border-white/5 mt-auto">
          <div className="flex gap-3 text-xs text-gray-500">
            <span>{mol.total_trials || 0} trials</span>
            {mol.pubmed_result_count > 0 && <span className="text-blue-400">{mol.pubmed_result_count} pubs</span>}
          </div>
          {mol.ip_status && <span className={`text-xs px-2 py-0.5 rounded-full ${ipStyle}`}>IP {mol.ip_status}</span>}
        </div>
      </div>
    </Link>
  );
}

export default function MoleculesPage() {
  const [molecules, setMolecules] = useState<any[]>([]);
  const [stats, setStats]         = useState<any>(null);
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(1);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState("");
  const [modality, setModality]   = useState("");
  const [minScore, setMinScore]   = useState("");
  const [ipStatus, setIpStatus]   = useState("");
  const [hasPubs, setHasPubs]     = useState(false);
  const PAGE_SIZE = 24;

  const fetchMolecules = async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size: PAGE_SIZE };
      if (search)   params.search = search;
      if (modality) params.modality = modality;
      if (minScore) params.min_score = minScore;
      if (ipStatus) params.ip_status = ipStatus;
      if (hasPubs)  params.has_publications = true;
      const res = await axios.get(`${API}/molecules/`, { params });
      setMolecules(res.data.results);
      setTotal(res.data.total);
    } catch (e) { setMolecules([]); }
    finally { setLoading(false); }
  };

  useEffect(() => { axios.get(`${API}/molecules/stats`).then(r => setStats(r.data)).catch(() => {}); }, []);
  useEffect(() => { fetchMolecules(); }, [page, search, modality, minScore, ipStatus, hasPubs]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <Layout>
      <div className="max-w-screen-2xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Molecule Library</h1>
            <p className="text-gray-400 text-sm mt-1">Deduplicated drug molecules from failed trials — ranked by rescue potential</p>
          </div>
          <button
            onClick={() => window.open(`${API}/molecules/export`, "_blank")}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            ↓ BD Export
          </button>
        </div>

        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: "Molecules",      value: stats.total_molecules },
              { label: "Resolved",       value: `${((stats.resolution_rate || 0) * 100).toFixed(0)}%` },
              { label: "Avg Score",      value: stats.avg_salvageability },
              { label: "IP Expired",     value: stats.by_ip_status?.expired || 0 },
              { label: "IP Active",      value: stats.by_ip_status?.active || 0 },
            ].map(s => (
              <div key={s.label} className="bg-white/5 border border-white/10 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-white">{s.value}</div>
                <div className="text-xs text-gray-500 mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-6">
          <div className="w-48 shrink-0 space-y-4">
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Search</label>
              <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
                placeholder="Name..." className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-white/30" />
            </div>
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Modality</label>
              <select value={modality} onChange={e => { setModality(e.target.value); setPage(1); }}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
                <option value="">All</option>
                {MODALITIES.map(m => <option key={m} value={m}>{m.replace("_", " ")}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Min Score</label>
              <input type="number" value={minScore} onChange={e => { setMinScore(e.target.value); setPage(1); }}
                placeholder="0" min={0} max={100} className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none" />
            </div>
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">IP Status</label>
              <select value={ipStatus} onChange={e => { setIpStatus(e.target.value); setPage(1); }}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
                <option value="">All</option>
                <option value="expired">Expired</option>
                <option value="active">Active</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={hasPubs} onChange={e => { setHasPubs(e.target.checked); setPage(1); }} />
              <span className="text-sm text-gray-300">Has publications</span>
            </label>
            <button onClick={() => { setSearch(""); setModality(""); setMinScore(""); setIpStatus(""); setHasPubs(false); setPage(1); }}
              className="text-xs text-gray-500 hover:text-gray-300">Clear filters</button>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm text-gray-500">{loading ? "Loading..." : `${total} molecules`}</span>
              {totalPages > 1 && (
                <div className="flex items-center gap-2">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    className="px-3 py-1 text-xs bg-white/5 border border-white/10 rounded disabled:opacity-30 text-white">Prev</button>
                  <span className="text-xs text-gray-400">{page}/{totalPages}</span>
                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                    className="px-3 py-1 text-xs bg-white/5 border border-white/10 rounded disabled:opacity-30 text-white">Next</button>
                </div>
              )}
            </div>
            {loading ? (
              <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {Array.from({ length: 12 }).map((_, i) => <div key={i} className="bg-white/5 border border-white/10 rounded-xl h-48 animate-pulse" />)}
              </div>
            ) : molecules.length === 0 ? (
              <div className="text-center py-20 text-gray-500">
                <p>No molecules found. Try adjusting filters or run ingestion first.</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {molecules.map(mol => <MoleculeCard key={mol.id} mol={mol} />)}
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}
