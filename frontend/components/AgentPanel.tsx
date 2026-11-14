"use client";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { AgentEvent } from "@/lib/api";

const SUGGESTIONS = [
  "Does parking track building occupancy?",
  "Which buildings are leased but empty?",
  "Does a sharp drop in parking come before occupancy falls?",
  "Does parking track occupancy for offices in Houston?",
  "Does parking usage predict lease renewals?",
  "Only Class A offices in LA?",
  "Is the link stronger in Houston or LA?",
  "Where does the link hold strongest?",
  "Is the result robust?",
];

const TOOL_LABEL: Record<string, string> = {
  build_lease_events: "built the lease-expiry table",
  usage_vs_renewal: "binned renewal rate by usage",
  regression: "ran the logistic regression",
  lead_time: "swept lead times",
  validate: "ran the validation suite",
  compare_groups: "compared groups",
  run_sql: "queried the data",
  regional_series: "built the regional time series",
  imagery_quality: "checked imagery quality",
  example_buildings: "pulled example buildings",
  submarket_context: "pulled submarket context",
  occupancy_link: "compared lot usage with CoStar occupancy, building by building",
  shadow_vacancy_screen: "ranked buildings by leased vs used",
  occupancy_lead_lag: "checked timing: occupancy before, at and after each capture",
  occupancy_after_drop: "followed occupancy after sharp lot drops",
  occupancy_by_group: "split the link by group",
};

function inline(s: string): ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part.replace(/^\*|\*$/g, "")}</Fragment>,
  );
}

function Note({ md }: { md: string }) {
  const paras = md.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return (
    <div className="final">
      {paras.map((p, i) =>
        p.startsWith("#") ? <h3 key={i}>{p.replace(/^#+\s*/, "")}</h3> :
        p.startsWith("*") && !p.startsWith("**") ? <p key={i}><em>{p.replace(/^\*|\*$/g, "")}</em></p> :
        <p key={i}>{inline(p)}</p>,
      )}
    </div>
  );
}

function describeArgs(args: Record<string, unknown>) {
  const parts = Object.entries(args)
    .filter(([k]) => !["include_noise_test", "limit", "n"].includes(k))
    .map(([k, v]) => (k === "watch_only" ? "watchlist only" : k === "min_lease_share" ? `tenants ${Math.round(Number(v) * 100)}%+ of building` :
      k === "by" ? `by ${String(v).replace("_", " ")}` : k === "exclude_covid" ? "without 2020-21" : String(v)));
  return parts.length ? ` (${parts.join(", ")})` : "";
}

export type Turn = { question: string; events: AgentEvent[] };

export default function AgentPanel({ turns, running, onAsk }: {
  turns: Turn[];
  running: boolean;
  onAsk: (q: string) => void;
}) {
  const [q, setQ] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const last = turns[turns.length - 1];
  const plan = last ? [...last.events].reverse().find((e) => e.type === "plan") : undefined;

  return (
    <>
      <div className="col-head">
        <h2>Agent reasoning</h2>
      </div>
      <div className="col-body" aria-live="polite">
        {!turns.length && (
          <div className="empty">
            <p>Ask how parking relates to tenants: occupancy, sharp drops, lease renewals. The agent plans the
              analysis, runs it on every measurable building, and shows what it excluded and why.</p>
          </div>
        )}
        {plan && plan.type === "plan" && running && (
          <ul className="plan" aria-label="Plan">
            {plan.todos.map((t, i) => (
              <li key={i} data-s={t.status}><span className="tick" />{t.content}</li>
            ))}
          </ul>
        )}
        <div className="log">
          {turns.map((t, ti) => (
            <Fragment key={ti}>
              <p className="q">{t.question}</p>
              {t.events.map((e, i) => {
                if (e.type === "step")
                  return <div key={i} className="step"><b>{e.agent.replace(/-/g, " ")}</b> {TOOL_LABEL[e.tool] ?? e.tool}{describeArgs(e.args)}</div>;
                if (e.type === "note") return <p key={i} className="note">{e.text}</p>;
                if (e.type === "error") return <p key={i} className="note err">{e.text}</p>;
                if (e.type === "final") return <Note key={i} md={e.text} />;
                return null;
              })}
            </Fragment>
          ))}
          <div ref={end} />
        </div>
      </div>
      <div className="ask">
        <div className="suggest">
          {SUGGESTIONS.filter((s) => !turns.some((t) => t.question === s)).slice(0, 4).map((s) => (
            <button key={s} type="button" disabled={running} onClick={() => onAsk(s)}>{s}</button>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) { onAsk(q.trim()); setQ(""); } }}>
          <label htmlFor="ask" style={{ position: "absolute", left: -9999 }}>Question</label>
          <input id="ask" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Only retail in Houston, without 2020-21?" />
          <button type="submit" disabled={running || !q.trim()}>{running ? "Working" : "Ask"}</button>
        </form>
      </div>
    </>
  );
}
