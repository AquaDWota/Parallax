"use client";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { AgentEvent } from "@/lib/api";

const SUGGESTIONS = [
  "Does parking track building occupancy?",
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
    .filter(([k]) => k !== "include_noise_test")
    .map(([k, v]) => (k === "min_lease_share" ? `tenants ${Math.round(Number(v) * 100)}%+ of building` :
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
  const conversation = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  useEffect(() => { followLatest.current = true; }, [turns.length]);
  useEffect(() => {
    const node = conversation.current;
    if (node && followLatest.current) node.scrollTop = node.scrollHeight;
  }, [turns]);
  const send = () => {
    if (running || !q.trim()) return;
    onAsk(q.trim());
    setQ("");
  };

  return (
    <>
      <div className="col-head chat-heading">
        <div><h2>Ask Parallax</h2><p>Explore the results in conversation.</p></div>
        <span className="chat-status" role="status">{running ? "Analyzing..." : "Ready"}</span>
      </div>
      <div className="col-body chat-messages" ref={conversation} role="log" aria-label="Conversation with Parallax" aria-live="polite"
        onScroll={() => { const node = conversation.current; if (node) followLatest.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80; }}>
        {!turns.length && (
          <div className="chat-welcome">
            <strong>What would you like to understand?</strong>
            <p>Ask about a city, a building, or a result. Charts and tables update in the larger Results panel.</p>
          </div>
        )}
        {turns.map((turn, index) => {
          const answer = [...turn.events].reverse().find((event) => event.type === "final");
          const errors = turn.events.filter((event) => event.type === "error");
          const active = running && index === turns.length - 1;
          const steps = turn.events.filter((event) => event.type === "step" || event.type === "note" || event.type === "plan");
          return (
            <div className="chat-turn" key={index}>
              <div className="chat-message from-user"><span className="message-author">You</span><p>{turn.question}</p></div>
              <div className="chat-message from-assistant">
                <span className="message-author">Parallax</span>
                {answer && answer.type === "final" ? <Note md={answer.text} /> :
                  active ? <p className="chat-thinking" role="status">Checking the data and updating your results...</p> :
                  !errors.length ? <p>The analysis is complete. See the updated results.</p> : null}
                {errors.map((error, errorIndex) => error.type === "error" && <p className="chat-error" role="alert" key={errorIndex}>{error.text}</p>)}
                {steps.length > 0 && (
                  <details className="chat-steps">
                    <summary>{active ? "View analysis progress" : "View analysis steps"}</summary>
                    {steps.map((event, stepIndex) => {
                      if (event.type === "step") return <p key={stepIndex}>{TOOL_LABEL[event.tool] ?? event.tool}{describeArgs(event.args)}</p>;
                      if (event.type === "note") return <p key={stepIndex}>{event.text}</p>;
                      if (event.type === "plan") return <ul key={stepIndex}>{event.todos.map((todo, todoIndex) => <li key={todoIndex}>{todo.content} ({todo.status.replace(/_/g, " ")})</li>)}</ul>;
                      return null;
                    })}
                  </details>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="ask chat-composer">
        <div className="suggest" aria-label="Suggested questions">
          {SUGGESTIONS.filter((suggestion) => !turns.some((turn) => turn.question === suggestion)).slice(0, turns.length ? 2 : 3).map((suggestion) => (
            <button key={suggestion} type="button" disabled={running} onClick={() => onAsk(suggestion)}>{suggestion}</button>
          ))}
        </div>
        <form onSubmit={(event) => { event.preventDefault(); send(); }}>
          <label htmlFor="ask" className="visually-hidden">Ask a question about the results</label>
          <textarea id="ask" rows={2} value={q} onChange={(event) => setQ(event.target.value)}
            placeholder="Ask about these results..."
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }} />
          <button type="submit" disabled={running || !q.trim()} aria-label="Send question">{running ? "Working..." : "Send"}</button>
        </form>
        <p className="composer-hint">Enter to send. Shift + Enter for a new line.</p>
      </div>
    </>
  );
}
