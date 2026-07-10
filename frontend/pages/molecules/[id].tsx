import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import Layout from "../../components/Layout";
import { StatusChip, PhaseBadge } from "../../components/ui";
import axios from "axios";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const CATEGORY_COLORS: Record<string, string> = {
  "Business termination": "text-blue-400",
  "Recruitment failure":  "text-yellow-400",
  "Lack of efficacy":     "text-orange-400",
  "Toxicity":             "text-red-400",
  "Endpoint failure":     "text-purple-400",
  "Operational issue":    "text-gray-400",
  "Unknown":              "text-gray-500",
};

const APPROVAL_COLORS: Record<string, string> = {
  approved:        "bg-green-500/20 text-green-300 border-green-500/30",
  investigational: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  withdrawn:       "bg-red-500/20 text-red-300 border-red-500/30",
  unknown:         "bg-gray-500/20 text-gray-400 border-gray-500/30",
};

const SOURCE_LABELS: Record<string, string> = {
  opentargets: "OpenTargets",
  drugbank:    "DrugBank",
};

function ScoreGauge({ score }: { score: number }) {
  const color = score >= 70 ? "#22c55e" : score >= 45 ? "#f59e0b" : "#ef4444";
  const r = 36, c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;
  return (
    <div className="flex flex-col items-center">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="8" />
        <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={c} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 50 50)" />
        <text x="50" y="55" textAnchor="middle" fill={color} fontSize="20" fontWeight="bold">{score}</text>
      </svg>
      <span className="text-xs text-gray-500 -mt-1">/ 100</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, value }: { label: string; value: any }) {
  if (!value && value !== 0) return null;
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="text-sm text-white mt-0.5">{value}</dd>
    </div>
  );
}

export default function MoleculeDetailPage() {
  const router = useRouter();
  const { id }  = router.query;
  const [mol, setMol]               = useState<any>(null);
  const [timeline, setTimeline]     = useState<any>(null);
  const [rwu, setRwu]               = useState<any>(null);
  const [loading, setLoading]       = useState(true);
  const [genLoading, setGenLoading] = useState(false);
  const [genMsg, setGenMsg]         = useState("");

  const fetchMolecule = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API}/molecules/${id}`);
      setMol(res.data);
    } catch { setMol(null); }
    finally { setLoading(false); }
  };

  const fetchTimelineAndUsage = async () => {
    if (!id) return;
    try {
      const res = await axios.get(`${API}/molecules/${id}/timeline`);
      setTimeline(res.data);
    } catch { setTimeline(null); }
    try {
      const res = await axios.get(`${API}/molecules/${id}/real-world-usage`);
      setRwu(res.data);
    } catch { setRwu(null); }
  };

  useEffect(() => { fetchMolecule(); fetchTimelineAndUsage(); }, [id]);

  const generateHypotheses = async () => {
    setGenLoading(true);
    setGenMsg("");
    try {
      const res = await axios.post(`${API}/molecules/${id}/hypotheses`);
      if (res.data.status === "cached") {
        setMol((m: any) => ({ ...m, repurposing_hypotheses: res.data.hypotheses }));
      } else {
        setGenMsg("Generating... refresh in ~10 seconds.");
        setTimeout(fetchMolecule, 12000);
      }
    } catch { setGenMsg("Generation failed. Try again."); }
    finally { setGenLoading(false); }
  };

  if (loading) return (
    <Layout>
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-4">
        {[...Array(4)].map((_, i) => <div key={i} className="bg-white/5 rounded-xl h-32 animate-pulse" />)}
      </div>
    </Layout>
  );

  if (!mol) return (
    <Layout>
      <div className="max-w-5xl mx-auto px-6 py-20 text-center text-gray-500">
        Molecule not found. <Link href="/molecules" className="text-blue-400 hover:underline">Back to library</Link>
      </div>
    </Layout>
  );

  return (
    <Layout>
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">

        {/* Breadcrumb */}
        <div className="text-sm text-gray-500">
          <Link href="/molecules" className="hover:text-white transition-colors">Molecules</Link>
          <span className="mx-2">/</span>
          <span className="text-gray-300">{mol.canonical_name}</span>
        </div>

        {/* Header card */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-6">
          <div className="flex items-start gap-6">
            {mol.best_salvageability != null && <ScoreGauge score={mol.best_salvageability} />}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-bold text-white">{mol.canonical_name}</h1>
                {mol.modality && (
                  <span className="text-xs px-2 py-1 bg-white/10 rounded-full text-gray-300">
                    {mol.modality.replace("_", " ")}
                  </span>
                )}
                {mol.ip_status && (
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    mol.ip_status === "expired" ? "bg-green-500/20 text-green-300" :
                    mol.ip_status === "active"  ? "bg-red-500/20 text-red-300" :
                    "bg-gray-500/20 text-gray-400"
                  }`}>
                    IP {mol.ip_status}
                  </span>
                )}
                {mol.approval_status && mol.approval_status !== "unknown" && (
                  <span className={`text-xs px-2 py-1 rounded-full border ${APPROVAL_COLORS[mol.approval_status] || APPROVAL_COLORS.unknown}`}>
                    {mol.approval_status === "approved" ? "✓ Approved elsewhere" : mol.approval_status}
                  </span>
                )}
              </div>
              {mol.inn_name && mol.inn_name !== mol.canonical_name && (
                <p className="text-gray-400 text-sm mt-1">INN: {mol.inn_name}</p>
              )}
              {mol.mechanism_of_action && (
                <p className="text-gray-300 text-sm mt-2">{mol.mechanism_of_action}</p>
              )}
              {mol.primary_targets?.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {mol.primary_targets.map((t: string) => (
                    <span key={t} className="text-xs bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded text-blue-300">{t}</span>
                  ))}
                </div>
              )}
            </div>
            <div className="text-right text-sm space-y-1 shrink-0">
              <div className="text-gray-500">{mol.total_trials} trial{mol.total_trials !== 1 ? "s" : ""}</div>
              <div className="text-gray-500">{mol.total_indications} indication{mol.total_indications !== 1 ? "s" : ""}</div>
              {mol.pubmed_result_count > 0 && <div className="text-blue-400">{mol.pubmed_result_count} publications</div>}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Left column */}
          <div className="lg:col-span-1 space-y-6">

            {/* Chemical identity */}
            <Section title="Chemical Identity">
              <dl className="space-y-3">
                <Field label="PubChem CID"   value={mol.pubchem_cid} />
                <Field label="ChEMBL ID"     value={mol.chembl_id} />
                <Field label="InChIKey"       value={mol.inchi_key} />
                <Field label="Mol. Weight"   value={mol.molecular_weight ? `${mol.molecular_weight} Da` : null} />
                <Field label="LogP"          value={mol.logp} />
                {mol.smiles && (
                  <div>
                    <dt className="text-xs text-gray-500">SMILES</dt>
                    <dd className="text-xs text-gray-400 mt-0.5 font-mono break-all">{mol.smiles}</dd>
                  </div>
                )}
              </dl>
              <div className="flex gap-2 mt-4 flex-wrap">
                {mol.pubchem_cid && (
                  <a href={`https://pubchem.ncbi.nlm.nih.gov/compound/${mol.pubchem_cid}`} target="_blank" rel="noreferrer"
                    className="text-xs text-blue-400 hover:text-blue-300 underline">PubChem ↗</a>
                )}
                {mol.chembl_id && (
                  <a href={`https://www.ebi.ac.uk/chembl/compound_report_card/${mol.chembl_id}/`} target="_blank" rel="noreferrer"
                    className="text-xs text-blue-400 hover:text-blue-300 underline">ChEMBL ↗</a>
                )}
              </div>
            </Section>

            {/* Patent */}
            <Section title="Patent & IP">
              {mol.patents?.length > 0 ? (
                <div className="space-y-3">
                  {mol.patents.slice(0, 5).map((p: any) => (
                    <div key={p.id} className="border border-white/5 rounded-lg p-3">
                      <p className="text-xs text-white font-medium line-clamp-2">{p.title || p.patent_number}</p>
                      <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-500 flex-wrap">
                        {p.patent_number && <span>{p.patent_number}</span>}
                        {p.assignee && <span>· {p.assignee}</span>}
                        {p.expiry_date && <span>· Exp {p.expiry_date}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500">No patent records found yet.<br />
                  <span className="text-xs">Patents are fetched in background after ingestion.</span>
                </p>
              )}
            </Section>
            {/* Real-world usage — approved/investigational indications elsewhere */}
            <Section title="Real-World Usage">
              {rwu?.indications?.length > 0 ? (
                <div className="space-y-2">
                  {rwu.indications.map((r: any, i: number) => (
                    <div key={i} className="border border-white/5 rounded-lg p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm text-white font-medium">{r.indication}</p>
                        <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${APPROVAL_COLORS[r.approval_status] || APPROVAL_COLORS.unknown}`}>
                          {r.approval_status || "unknown"}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-500">
                        <span>{SOURCE_LABELS[r.source] || r.source}</span>
                        {r.region && <span>· {r.region}</span>}
                        {r.approved_date && <span>· {String(r.approved_date).slice(0, 4)}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  No approved/investigational indications found yet.<br />
                  <span className="text-xs">Sourced from OpenTargets{rwu?.drugbank_id ? " and DrugBank" : ""}.</span>
                </p>
              )}
            </Section>
          </div>

          {/* Right column */}
          <div className="lg:col-span-2 space-y-6">

            {/* Trial timeline — "when and where it was used" */}
            <Section title="Trial Timeline">
              {timeline?.trials?.length > 0 ? (
                <div className="space-y-3">
                  {(timeline.first_studied || timeline.last_active) && (
                    <p className="text-xs text-gray-500 mb-2">
                      Studied {timeline.first_studied ? String(timeline.first_studied).slice(0, 10) : "—"}
                      {" → "}
                      {timeline.last_active ? String(timeline.last_active).slice(0, 10) : "—"}
                    </p>
                  )}
                  {timeline.trials.map((t: any) => (
                    <div key={t.nct_id} className="border border-white/5 rounded-lg p-3">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <Link href={`/trials/${t.nct_id}`}>
                          <span className="text-xs text-gray-500 font-mono hover:text-blue-400 cursor-pointer">{t.nct_id}</span>
                        </Link>
                        <div className="flex items-center gap-2">
                          <PhaseBadge phase={t.phase} />
                          <StatusChip status={t.status} />
                        </div>
                      </div>
                      <p className="text-sm text-gray-300 mt-1.5">{t.indication || "—"}</p>
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500 flex-wrap">
                        {t.sponsor && <span>{t.sponsor}</span>}
                        {(t.start_date || t.completion_date) && (
                          <span>
                            {t.start_date ? String(t.start_date).slice(0, 10) : "?"}
                            {" – "}
                            {t.completion_date ? String(t.completion_date).slice(0, 10) : "?"}
                          </span>
                        )}
                        <span className={CATEGORY_COLORS[t.failure_category] || "text-gray-500"}>
                          {t.failure_category || "—"}
                        </span>
                        {t.salvageability_score != null && (
                          <span className={`font-bold ${
                            t.salvageability_score >= 70 ? "text-green-400" :
                            t.salvageability_score >= 45 ? "text-yellow-400" : "text-red-400"
                          }`}>{t.salvageability_score}</span>
                        )}
                      </div>
                      {t.why_stopped && (
                        <p className="text-xs text-gray-500 mt-1.5 italic line-clamp-2">"{t.why_stopped}"</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : mol.trials?.length > 0 ? (
                // Fallback for trials ingested before the timeline fields existed
                <div className="space-y-2">
                  {mol.trials.map((t: any) => (
                    <Link key={t.nct_id} href={`/trials/${t.nct_id}`}>
                      <div className="flex items-center justify-between p-3 bg-white/3 rounded-lg hover:bg-white/5 transition-colors cursor-pointer">
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-xs text-gray-500 font-mono shrink-0">{t.nct_id}</span>
                          <span className="text-sm text-gray-300 truncate">{t.indication || "—"}</span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0 ml-2">
                          <span className="text-xs text-gray-500">{t.phase || "—"}</span>
                          <span className={`text-xs ${CATEGORY_COLORS[t.failure_category] || "text-gray-500"}`}>
                            {t.failure_category || "—"}
                          </span>
                          {t.salvageability_score != null && (
                            <span className={`text-sm font-bold ${
                              t.salvageability_score >= 70 ? "text-green-400" :
                              t.salvageability_score >= 45 ? "text-yellow-400" : "text-red-400"
                            }`}>{t.salvageability_score}</span>
                          )}
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : <p className="text-sm text-gray-500">No linked trials.</p>}
            </Section>

            {/* Repurposing hypotheses */}
            <Section title="Repurposing Hypotheses">
              {mol.repurposing_hypotheses?.length > 0 ? (
                <div className="space-y-3">
                  {mol.repurposing_hypotheses.map((h: string, i: number) => (
                    <div key={i} className="flex gap-3">
                      <span className="text-gray-600 text-sm shrink-0">{i + 1}.</span>
                      <p className="text-sm text-gray-300 leading-relaxed">{h}</p>
                    </div>
                  ))}
                  <button onClick={generateHypotheses} disabled={genLoading}
                    className="text-xs text-gray-500 hover:text-gray-300 mt-2 transition-colors">
                    Regenerate
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-gray-500">No hypotheses generated yet.</p>
                  <button onClick={generateHypotheses} disabled={genLoading}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors">
                    {genLoading ? "Generating..." : "Generate with AI"}
                  </button>
                  {genMsg && <p className="text-xs text-gray-400">{genMsg}</p>}
                </div>
              )}
            </Section>

            {/* Literature */}
            {mol.literature?.length > 0 && (
              <Section title="PubMed Literature">
                <div className="space-y-3">
                  {mol.literature.slice(0, 8).map((pub: any) => (
                    <div key={pub.pmid} className="border-b border-white/5 pb-3 last:border-0">
                      <a href={`https://pubmed.ncbi.nlm.nih.gov/${pub.pmid}/`} target="_blank" rel="noreferrer"
                        className="text-sm text-blue-400 hover:text-blue-300 leading-snug block">
                        {pub.title}
                      </a>
                      <div className="flex gap-3 text-xs text-gray-500 mt-1">
                        {pub.journal && <span>{pub.journal}</span>}
                        {pub.pub_date && <span>{String(pub.pub_date).slice(0, 4)}</span>}
                        <span className={pub.ref_type === "result" ? "text-green-400" : "text-gray-500"}>
                          {pub.ref_type}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}