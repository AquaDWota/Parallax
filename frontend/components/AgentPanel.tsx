"use client";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { AgentEvent } from "@/lib/api";
import EvidenceCards, { evidenceFrom, watchCountFrom } from "./EvidenceCards";

const SUGGESTIONS = [
  "Does parking track building occupancy?",
  "Which buildings are leased but empty?",
  "Which buildings look like investment opportunities?",
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

/** Plain text from LaTeX the model sometimes writes: $p<0.001$ -> p<0.001, \times -> x. */
function unlatex(s: string) {
  return s.replace(/\$([^$]+)\$/g, "$1").replace(/\\(times|cdot)/g, "x").replace(/\\%/g, "%").replace(/\\(text|mathrm)\{([^}]*)\}/g, "$2");
}

function inline(s: string): ReactNode[] {
  return unlatex(s).split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <Fragment key={i}>{part.replace(/(^|\s)\*([^*\s][^*]*)\*(?=\s|$|[.,;:])/g, "$1$2")}</Fragment>,
  );
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

/** Minimal markdown for the agent's note: headings, paragraphs, bullet/numbered lists, tables. */
function Note({ md }: { md: string }) {
  const lines = md.replace(/\r/g, "").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line || /^(-{3,}|\*{3,})$/.test(line)) { i++; continue; }
    if (line.startsWith("#")) { out.push(<h3 key={i}>{inline(line.replace(/^#+\s*/, ""))}</h3>); i++; continue; }
    if (line.startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++].trim());
      const body = rows.filter((r) => !/^\|?[\s:|-]+\|?$/.test(r)); // drop the |---|---| line
      const [head, ...rest] = body;
      out.push(
        <div className="tableWrap" key={i}>
          <table>
            {head && <thead><tr>{cells(head).map((c, k) => <th key={k}>{inline(c)}</th>)}</tr></thead>}
            <tbody>{rest.map((r, ri) => <tr key={ri}>{cells(r).map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\d/.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) items.push(lines[i++].trim().replace(/^([-*•]|\d+[.)])\s+/, ""));
      const li = items.map((t, k) => <li key={k}>{inline(t)}</li>);
      out.push(ordered ? <ol key={i}>{li}</ol> : <ul key={i}>{li}</ul>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#|\||([-*•]|\d+[.)])\s+)/.test(lines[i].trim())) para.push(lines[i++].trim());
    if (!para.length) { i++; continue; }
    out.push(<p key={i}>{inline(para.join(" "))}</p>);
  }
  return <div className="final">{out}</div>;
}

function describeArgs(args: Record<string, unknown>) {
  const parts = Object.entries(args)
    .filter(([k]) => !["include_noise_test", "limit", "n"].includes(k))
    .map(([k, v]) => (k === "watch_only" ? "risk flags only" : k === "min_lease_share" ? `tenants ${Math.round(Number(v) * 100)}%+ of building` :
      k === "by" ? `by ${String(v).replace("_", " ")}` : k === "exclude_covid" ? "without 2020-21" : String(v)));
  return parts.length ? ` (${parts.join(", ")})` : "";
}

export type Turn = { question: string; events: AgentEvent[] };

export default function AgentPanel({ turns, running, onAsk, onPickBuilding, onSeeWatchlist, screenRows }: {
  turns: Turn[];
  running: boolean;
  onAsk: (q: string) => void;
  onPickBuilding: (id: string) => void;
  onSeeWatchlist?: () => void;
  screenRows?: any[];
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
            <p className="lede">Ask how parking relates to tenants: occupancy, sharp drops, lease renewals, or which
              buildings look leased on paper but empty in the lot.</p>
            <ol className="how">
              <li><b>Plans the analysis</b><span>picks the tools and hands parts to helper agents</span></li>
              <li><b>Runs it on every measurable building</b><span>Vexcel car counts against CoStar tenancy records</span></li>
              <li><b>Shows the proof</b><span>lot photos then and now, and what it excluded and why</span></li>
            </ol>
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
                if (e.type === "final")
                  return (
                    <Fragment key={i}>
                      <Note md={e.text} />
                      <EvidenceCards items={evidenceFrom(t.events, screenRows)} onPick={onPickBuilding}
                        nWatch={watchCountFrom(t.events)} onSeeAll={onSeeWatchlist} />
                    </Fragment>
                  );
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
