"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, ShieldAlert, Zap, Lock, Link2, CheckCircle2, XCircle, Activity, Cpu, FlaskConical, Wallet } from "lucide-react";
import { API, j } from "../lib/api";

type Ev = { id: number; kind: string; agent: string; message: string; dispute_id?: string; data: any };
const TOKEN_RE = /(<(?:PAN|IBAN|SSN|EMAIL)_\d+>)/g;
const KIND_COLOR: Record<string, string> = {
  pii: "text-neon", agent: "text-sky-300", tool: "text-emeraldx", retry: "text-amberx", security: "text-red-400",
  hitl: "text-amberx", decision: "text-emeraldx", intake: "text-slate-400", llm: "text-amberx",
};

function Tokens({ text }: { text: string }) {
  return <>{text.split(TOKEN_RE).map((p, i) => i % 2 === 1
    ? <mark key={i} className="bg-neon/20 text-neon px-1 rounded">{p}</mark> : <span key={i}>{p}</span>)}</>;
}

export default function Page() {
  const [scenarios, setScenarios] = useState<Record<string, any>>({});
  const [payload, setPayload] = useState("");
  const [sim429, setSim429] = useState(0);
  const [raw, setRaw] = useState("");
  const [events, setEvents] = useState<Ev[]>([]);
  const [disputes, setDisputes] = useState<any[]>([]);
  const [ledger, setLedger] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [verify, setVerify] = useState<any>(null);
  const [harbor, setHarbor] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [role, setRole] = useState("senior_approver");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const streamRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const [d, l, a, m, h] = await Promise.allSettled([j("/disputes"), j("/ledger"), j("/audit?limit=40"), j("/metrics"), j("/harbor/results")]);
    if (d.status === "fulfilled") setDisputes(d.value);
    if (l.status === "fulfilled") setLedger(l.value);
    if (a.status === "fulfilled") setAudit(a.value);
    if (m.status === "fulfilled") setMetrics(m.value);
    if (h.status === "fulfilled") setHarbor(h.value);
  }, []);

  useEffect(() => { j("/scenarios").then(setScenarios).catch(() => setToast("Backend unreachable at " + API)); refresh(); }, [refresh]);
  useEffect(() => {
    const es = new EventSource(`${API}/stream/events`);
    es.onmessage = (m) => { setEvents((e) => [...e.slice(-120), JSON.parse(m.data)]); refresh(); };
    return () => es.close();
  }, [refresh]);
  useEffect(() => { streamRef.current?.scrollTo({ top: 1e9, behavior: "smooth" }); }, [events]);

  const run = async (text: string, s429 = 0) => {
    setRaw(text); setBusy(true);
    try { await j("/disputes/process", { method: "POST", body: JSON.stringify({ payload: text, simulate_429: s429 }) }); }
    catch (e: any) { setToast(e.message); } finally { setBusy(false); refresh(); }
  };
  const resolve = async (id: string, approve: boolean) => {
    try { await j(`/disputes/${id}/${approve ? "approve" : "reject"}`, { method: "POST", headers: { "X-Role": role }, body: JSON.stringify({ operator: "ops-console" }) }); setToast(approve ? "Refund authorized" : "Quarantined"); }
    catch (e: any) { setToast("Blocked: " + e.message); } refresh();
  };
  const doVerify = async () => setVerify(await j("/audit/verify"));
  const tamper = async () => { try { await j("/audit/tamper-demo/3", { method: "POST" }); setToast("Row 3 tampered (demo)"); } catch (e: any) { setToast(e.message); } doVerify(); };

  const tokenized = useMemo(() => [...events].reverse().find((e) => e.kind === "pii")?.data?.tokenized ?? "", [events]);
  const pending = disputes.filter((d) => d.status === "PENDING_APPROVAL");
  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(""), 3500); return () => clearTimeout(t); } }, [toast]);

  return (
    <main className="p-4 max-w-[1600px] mx-auto space-y-4">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3"><ShieldCheck className="text-neon" />
          <h1 className="text-xl tracking-widest text-neon">AEGISLEDGER <span className="text-slate-500">// RISK COMMAND CENTER</span></h1></div>
        <div className="flex gap-3 text-xs">
          <span className="glass px-3 py-1 flex items-center gap-2"><Cpu size={14} className="text-amberx" />{metrics?.engine ?? "…"}</span>
          <span className="glass px-3 py-1 flex items-center gap-2"><Lock size={14} className="text-neon" />{metrics?.pii_redactions ?? 0} PII redacted</span>
          <span className="glass px-3 py-1 flex items-center gap-2"><Activity size={14} className="text-emeraldx" />{metrics?.avg_llm_latency_ms ?? 0} ms avg</span>
        </div>
      </header>

      <div className="grid grid-cols-12 gap-4">
        {/* LEFT */}
        <section className="glass p-4 col-span-12 lg:col-span-3 space-y-3">
          <h2 className="text-xs tracking-widest text-slate-400 flex items-center gap-2"><Zap size={14} />LIVE DISPUTE INJECTOR</h2>
          {Object.entries(scenarios).map(([k, s]: any) => (
            <button key={k} disabled={busy} onClick={() => { setPayload(s.payload); setSim429(s.simulate_429); run(s.payload, s.simulate_429); }}
              className={`w-full text-left text-xs p-2 rounded border transition ${k === "injection" ? "border-red-500/40 hover:bg-red-500/10" : k.includes("2500") || k.includes("cross") ? "border-amberx/40 hover:bg-amberx/10" : "border-cyan-500/30 hover:bg-cyan-500/10"} disabled:opacity-40`}>
              {s.title}</button>))}
          <textarea value={payload} onChange={(e) => setPayload(e.target.value)} rows={8} placeholder="Custom dispute payload…"
            className="w-full bg-black/40 border border-cyan-500/20 rounded p-2 text-xs outline-none focus:border-neon" />
          <label className="text-xs flex items-center gap-2">Simulate ledger 429s
            <input type="number" min={0} max={4} value={sim429} onChange={(e) => setSim429(+e.target.value)} className="w-14 bg-black/40 border border-cyan-500/20 rounded px-1" /></label>
          <button disabled={busy || !payload} onClick={() => run(payload, sim429)} className="w-full py-2 text-xs rounded bg-neon/10 border border-neon/50 text-neon hover:bg-neon/20 disabled:opacity-40">PROCESS CUSTOM PAYLOAD</button>
        </section>

        {/* CENTER */}
        <section className="glass p-4 col-span-12 lg:col-span-5 space-y-3">
          <h2 className="text-xs tracking-widest text-slate-400 flex items-center gap-2"><ShieldAlert size={14} />PII FIREWALL — RAW vs ZERO-TRUST PAYLOAD</h2>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="bg-black/40 rounded p-2 border border-red-500/30 h-36 overflow-auto scroll"><div className="text-red-400 mb-1">RAW INCOMING (never leaves the vault)</div><pre className="whitespace-pre-wrap">{raw || "—"}</pre></div>
            <div className="bg-black/40 rounded p-2 border border-emeraldx/30 h-36 overflow-auto scroll"><div className="text-emeraldx mb-1">TOKENIZED → LLM</div><pre className="whitespace-pre-wrap">{tokenized ? <Tokens text={tokenized} /> : "—"}</pre></div>
          </div>
          <h2 className="text-xs tracking-widest text-slate-400 pt-1">AGENT NEURAL STREAM</h2>
          <div ref={streamRef} className="bg-black/40 rounded p-2 h-64 overflow-auto scroll text-[11px] space-y-1">
            <AnimatePresence initial={false}>{events.map((e) => (
              <motion.div key={e.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="flex gap-2">
                <span className={`${KIND_COLOR[e.kind] ?? ""} shrink-0 w-32 truncate`}>[{e.agent}]</span>
                <span>{e.message}{e.data?.latency_ms !== undefined && <span className="ml-2 px-1 rounded bg-emeraldx/10 text-emeraldx">{e.data.latency_ms}ms</span>}</span>
              </motion.div>))}</AnimatePresence>
            {!events.length && <div className="text-slate-500">Waiting for dispute…</div>}
          </div>
        </section>

        {/* RIGHT */}
        <section className="glass p-4 col-span-12 lg:col-span-4 space-y-3">
          <h2 className="text-xs tracking-widest text-amberx flex items-center gap-2"><ShieldAlert size={14} />HITL APPROVAL QUEUE</h2>
          <label className="text-xs flex items-center gap-2">Operator role
            <select value={role} onChange={(e) => setRole(e.target.value)} className="bg-black/60 border border-cyan-500/20 rounded px-1">
              <option>senior_approver</option><option>analyst</option></select></label>
          {!pending.length && <div className="text-xs text-slate-500">No pending approvals.</div>}
          {pending.map((d) => (
            <motion.div key={d.dispute_id} layout className="border border-amberx/50 bg-amberx/5 rounded p-3 text-xs space-y-2 shadow-[0_0_18px_#ffb80022]">
              <div className="flex justify-between"><b>{d.dispute_id}</b><span className="text-amberx">PENDING_APPROVAL</span></div>
              <div>{d.case.txn_id} · ${(d.case.amount_cents / 100).toLocaleString()}</div>
              <ul className="text-slate-300 list-disc pl-4">{d.decision.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
              <div className="flex gap-2">
                <button onClick={() => resolve(d.dispute_id, true)} className="flex-1 py-2 rounded bg-emeraldx/15 border border-emeraldx text-emeraldx hover:bg-emeraldx/30 active:scale-95 transition">AUTHORIZE REFUND</button>
                <button onClick={() => resolve(d.dispute_id, false)} className="flex-1 py-2 rounded bg-red-500/15 border border-red-500 text-red-400 hover:bg-red-500/30 active:scale-95 transition">BLOCK & QUARANTINE</button>
              </div></motion.div>))}
          <h2 className="text-xs tracking-widest text-slate-400 flex items-center gap-2 pt-2"><Wallet size={14} />DOUBLE-ENTRY LEDGER</h2>
          <div className="text-xs space-y-1">{ledger?.accounts.map((a: any) => (
            <div key={a.id} className="flex justify-between border-b border-white/5 py-0.5"><span>{a.id}{a.hold && <span className="ml-1 text-red-400">[HOLD]</span>}</span>
              <span className="text-neon">${(a.balance_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></div>))}
            {ledger && <div className="flex justify-between pt-1 text-slate-400"><span>Σ invariant</span><span className={ledger.entries_balanced ? "text-emeraldx" : "text-red-400"}>${(ledger.total_cents / 100).toLocaleString()} {ledger.entries_balanced ? "BALANCED" : "BROKEN"}</span></div>}
          </div>
          <div className="text-xs text-slate-400">Recent: {disputes.slice(0, 4).map((d) => <span key={d.dispute_id} className="mr-2">{d.dispute_id.slice(-4)}:{d.status}</span>)}</div>
        </section>
      </div>

      {/* BOTTOM DRAWER */}
      <section className="glass p-4 grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-8">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs tracking-widest text-slate-400 flex items-center gap-2"><Link2 size={14} />CRYPTOGRAPHIC AUDIT CHAIN (SHA-256)</h2>
            <div className="flex gap-2 items-center">
              {verify && <span className={`text-xs px-2 py-0.5 rounded ${verify.valid ? "bg-emeraldx/15 text-emeraldx" : "bg-red-500/20 text-red-400"}`}>{verify.valid ? `VERIFIED · ${verify.length} blocks` : `BROKEN at #${verify.broken_at}`}</span>}
              <button onClick={tamper} className="text-[10px] px-2 py-1 rounded border border-red-500/40 text-red-400 hover:bg-red-500/10">TAMPER DEMO</button>
              <button onClick={doVerify} className="text-xs px-3 py-1 rounded border border-emeraldx text-emeraldx hover:bg-emeraldx/20">VERIFY CHAIN INTEGRITY</button></div>
          </div>
          <div className="flex gap-2 overflow-x-auto scroll pb-2">
            {audit.map((a, i) => (
              <motion.div key={a.seq} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                className={`min-w-[170px] text-[10px] rounded border p-2 ${verify && !verify.valid && a.seq >= verify.broken_at ? "border-red-500/60" : "border-emeraldx/30"}`}>
                <div className="text-emeraldx">#{a.seq} {a.event_type}</div>
                <div className="text-slate-500 truncate">prev {a.prev_hash.slice(0, 10)}…</div>
                <div className="text-neon truncate">hash {a.hash.slice(0, 10)}…</div></motion.div>))}
          </div>
        </div>
        <div className="col-span-12 lg:col-span-4">
          <h2 className="text-xs tracking-widest text-slate-400 flex items-center gap-2 mb-2"><FlaskConical size={14} />HARBOR EVAL MATRIX {harbor?.available && <span className="text-emeraldx">score {harbor.score}</span>}</h2>
          {!harbor?.available && <div className="text-xs text-slate-500">Run ./harbor_eval/run_harbor.sh</div>}
          <div className="space-y-1 text-[11px] max-h-40 overflow-auto scroll">{harbor?.tasks?.map((t: any) => (
            <div key={t.task}><div className="flex items-center gap-1">{t.passed ? <CheckCircle2 size={12} className="text-emeraldx" /> : <XCircle size={12} className="text-red-400" />}{t.task}</div>
              <div className="pl-4 text-slate-500">{t.assertions.map((a: any) => <span key={a.name} className={`mr-2 ${a.passed ? "text-emeraldx/70" : "text-red-400"}`}>{a.name.replace("test_", "")}</span>)}</div></div>))}</div>
        </div>
      </section>
      <AnimatePresence>{toast && <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="fixed bottom-4 right-4 glass px-4 py-2 text-sm text-neon">{toast}</motion.div>}</AnimatePresence>
    </main>
  );
}
