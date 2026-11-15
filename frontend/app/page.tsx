"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import AgentPanel, { type Turn } from "@/components/AgentPanel";
import BuildingDrawer from "@/components/BuildingDrawer";
import ResultsPanel, { type Results } from "@/components/ResultsPanel";
import ParkingLegend from "@/components/ParkingLegend";
import Stalls from "@/components/Stalls";
import { api, askStream, usageColor, activityMultiple, type AgentEvent, type Building, type Meta } from "@/lib/api";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function Page() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [city, setCity] = useState("Houston");
  const [pi, setPi] = useState(0);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [running, setRunning] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [results, setResults] = useState<Results>({});
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    // ?b=<building id> opens that building (handy for demo links)
    const b = new URLSearchParams(window.location.search).get("b");
    if (b) api.building(b).then((x) => { setCity(x.city); setSelected(b); }).catch(() => {});
    api.meta().then((m) => {
      setMeta(m);
      const pre = m.periods.filter((p) => p < "2020");
      setPi(Math.max(0, m.periods.indexOf(pre[pre.length - 1] ?? m.periods[0])));
    })
      .catch(() => setLoadError("Can't reach the API on port 8000. Start it with: cd backend && uvicorn api.main:app --port 8000"));
    api.overview().then((o) => setResults({
      occLink: o.occ_link?.bins ? o.occ_link : undefined, occLead: o.occ_lead, occDrop: o.occ_drop,
      bins: o.bins, regression: o.regression, regional: o.regional,
    })).catch(() => {});
  }, []);

  const period = meta?.periods[pi];
  useEffect(() => {
    if (!period) return;
    api.buildings(period, city).then(setBuildings).catch(() => {});
  }, [period, city]);

  const summary = useMemo(() => {
    const m = buildings.filter((b) => b.abs_index != null);
    if (!m.length) return "";
    const med = [...m].sort((a, b) => a.abs_index! - b.abs_index!)[Math.floor(m.length / 2)].abs_index!;
    return `${m.length} lots measured, median activity ${activityMultiple(med, 2)} its pre-COVID reference`;
  }, [buildings]);

  const onEvent = useCallback((e: AgentEvent) => {
    setTurns((ts) => {
      const copy = ts.slice();
      const last = copy[copy.length - 1];
      copy[copy.length - 1] = { ...last, events: [...last.events, e] };
      return copy;
    });
    if (e.type === "result") {
      setResults((r) => {
        const d = e.data;
        switch (e.tool) {
          case "occupancy_link": return d.bins ? { ...r, occLink: d } : r;
          case "occupancy_lead_lag": return { ...r, occLead: d };
          case "occupancy_after_drop": return d.n_drops ? { ...r, occDrop: d } : r;
          case "occupancy_by_group": return d.groups ? { ...r, occGroups: d } : r;
          case "usage_vs_renewal": return d.bins ? { ...r, bins: d } : r;
          case "regression": return d.odds_ratio_per_10pt_drop ? { ...r, regression: d } : r;
          case "lead_time": return { ...r, lead: d };
          case "regional_series": return { ...r, regional: d };
          case "compare_groups": return d.groups ? { ...r, groups: [...(r.groups ?? []).filter((g) => g.by !== d.by), d] } : r;
          case "validate": return { ...r, validate: d };
          case "example_buildings": return { ...r, examples: d };
          default: return r;
        }
      });
    }
  }, []);

  const ask = useCallback(async (q: string) => {
    setRunning(true);
    setResults((r) => ({ regional: r.regional, bins: r.bins, regression: r.regression, occLink: r.occLink, occLead: r.occLead, occDrop: r.occDrop }));
    setTurns((ts) => [...ts, { question: q, events: [] }]);
    try {
      const history = turns.flatMap((turn) => {
        const answer = [...turn.events].reverse().find((event) => event.type === "final");
        return [{ role: "user" as const, content: turn.question }, ...(answer && answer.type === "final" ? [{ role: "assistant" as const, content: answer.text }] : [])];
      });
      await askStream(q, onEvent, undefined, history);
    } catch (err) {
      onEvent({ type: "error", text: `The agent stopped: ${String(err)}` });
    } finally {
      setRunning(false);
    }
  }, [onEvent, turns]);

  const pickBin = useCallback((b: { bin: number }, f: Record<string, any>) => {
    const args: Record<string, any> = { usage_bin: b.bin, n: 4, min_lease_share: f.min_lease_share ?? 0 };
    for (const k of ["city", "property_type", "building_class"]) if (f[k]) args[k] = f[k];
    api.tool("example_buildings", args).then((d) => setResults((r) => ({ ...r, examples: d })));
  }, []);

  const pickBuilding = useCallback((id: string) => {
    api.building(id).then((b) => { if (b.city !== city) setCity(b.city); });
    setSelected(id);
  }, [city]);

  return (
    <div className={`shell ${chatOpen ? "chat-is-open" : "chat-is-closed"}`}>
      <header className="topbar">
        <h1 className="wordmark">
          <span>Parallax</span>
          <svg className="brand-squirrel" viewBox="0 0 212 98" fill="none" role="img" aria-label="A cute flying squirrel peeking above the roof of Nassau Hall saying HackPrinceton">
            <path d="M12 87h132" stroke="#B4BFC4" strokeWidth="2" strokeLinecap="round" />
            {/* The squirrel sits behind the building; the facade hides its lower body. */}
            <g transform="translate(77 1) scale(0.83)">
              <path d="M47 31C58 31 69 22 65 12 62 4 49 6 47 14c-2 6 7 7 8 2 4 7-4 10-10 10" fill="#C48857" stroke="#704931" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
              {/* Round belly, one relaxed arm and one raised waving paw. */}
              <ellipse cx="34" cy="43" rx="16" ry="17" fill="#C48857" stroke="#704931" strokeWidth="2.2" />
              <ellipse cx="33" cy="43" rx="11" ry="14" fill="#F9E8CE" />
              <g transform="translate(68 0) scale(-1 1)">
              <path d="M23 35q-9 4-8 14" stroke="#704931" strokeWidth="8" strokeLinecap="round" />
              <path d="M23 35q-9 4-8 14" stroke="#C48857" strokeWidth="4" strokeLinecap="round" />
              <path d="M47 35q10-3 10-15" stroke="#704931" strokeWidth="8" strokeLinecap="round" />
              <path d="M47 35q10-3 10-15" stroke="#C48857" strokeWidth="4" strokeLinecap="round" />
              <ellipse cx="57" cy="17" rx="4.5" ry="6" transform="rotate(-10 57 17)" fill="#C48857" stroke="#704931" strokeWidth="1.7" />
              <path d="m69 14 2-3m-3 13 4 1" stroke="#D6A059" strokeWidth="1.7" strokeLinecap="round" />
              </g>
              <path d="m20 19-1-9c0-4 4-5 7-1l4 6m9 3 5-7c3-4 7-2 6 2l-2 10" fill="#C48857" stroke="#704931" strokeWidth="2.2" strokeLinejoin="round" />
              <path d="m22 12 4 6-4 1m24-5-4 6 4 1" fill="#EAB4A5" />
              <ellipse cx="34" cy="24" rx="16" ry="13" transform="rotate(12 34 24)" fill="#C48857" stroke="#704931" strokeWidth="2.2" />
              <ellipse cx="32" cy="29" rx="10" ry="7" transform="rotate(12 32 29)" fill="#F9E8CE" />
              <ellipse cx="27" cy="22" rx="2.6" ry="3.4" fill="#382B28" /><ellipse cx="41" cy="25" rx="2.6" ry="3.4" fill="#382B28" />
              <circle cx="27.7" cy="21" r="0.9" fill="white" /><circle cx="41.7" cy="24" r="0.9" fill="white" />
              <ellipse cx="23" cy="27" rx="3" ry="1.8" fill="#E99B8A" /><ellipse cx="44" cy="30" rx="3" ry="1.8" fill="#E99B8A" />
              <path d="m31 28 5 1-3 3Z" fill="#704931" stroke="#704931" strokeLinejoin="round" />
              <path d="M29 33q3 4 7 1" stroke="#704931" strokeWidth="1.5" strokeLinecap="round" />
            </g>
            {/* Nassau Hall's stone facade, central pediment and cupola. */}
            <path d="M18 53h112v33H18Z" fill="#C7AD87" stroke="#705C48" strokeWidth="1.5" />
            <path d="m13 53 8-7h107l8 7Z" fill="#61716A" stroke="#46574F" strokeWidth="1.5" />
            <path d="M62 50h25v36H62Z" fill="#DBC6A5" stroke="#705C48" strokeWidth="1.5" />
            <path d="m57 50 18-11 17 11Z" fill="#E6D6BB" stroke="#705C48" strokeWidth="1.5" />
            <path d="M69 31h12v11H69Z" fill="#E6D6BB" stroke="#705C48" strokeWidth="1.5" />
            <path d="M67 31q8-16 16 0Z" fill="#61716A" stroke="#46574F" strokeWidth="1.5" />
            <path d="M75 21v-7" stroke="#46574F" strokeWidth="1.5" />
            <path d="m75 14 11 3-11 3Z" fill="#ED8B23" />
            <path d="M72 34h6v6h-6Z" fill="#43515B" />
            {[27, 41, 99, 113].map((x) => <g key={x} fill="#43515B"><rect x={x} y="58" width="6" height="8" rx="0.6" /><rect x={x} y="72" width="6" height="8" rx="0.6" /></g>)}
            <path d="M69 86V73a6 6 0 0 1 12 0v13" fill="#594A3F" />
            <path d="M71 55h7v8h-7Z" fill="#43515B" />
            {/* Keep the label as real SVG text so it stays crisp at every size. */}
            <path d="M123 1h80a7 7 0 0 1 7 7v18a7 7 0 0 1-7 7h-67l-13 9 3-9h-3a7 7 0 0 1-7-7V8a7 7 0 0 1 7-7Z" fill="#FFF9EF" stroke="#704931" strokeWidth="1.5" strokeLinejoin="round" />
            <text x="163" y="21" textAnchor="middle" fill="#5D3823" fontFamily="Arial, sans-serif" fontSize="10" fontWeight="700">HackPrinceton</text>
          </svg>
        </h1>
        <p className="thesis">Parking lots as a live occupancy gauge: Vexcel aerial car counts against CoStar tenancies, Houston and LA, 2016 to 2026.</p>
        {meta && <span className="mode">{meta.data_mode === "synthetic" ? "Synthetic data" : "Real Vexcel + CoStar data"}, {meta.agent_mode === "llm" ? "LLM planner" : "scripted planner"}</span>}
      </header>

      <main className="grid">
        <section className="col map-column" aria-label="Map">
          <div className="col-head">
            <h2>Parking relative to its baseline</h2>
            <div className="citypick" role="group" aria-label="City">
              {(meta?.cities ?? ["Houston", "Los Angeles"]).map((c) => (
                <button key={c} type="button" aria-pressed={c === city} onClick={() => { setCity(c); setSelected(null); }}>{c}</button>
              ))}
            </div>
          </div>
          <div className="map-year-bar" role="status" aria-label="Selected year" aria-live="polite" aria-atomic="true">
            <strong>{period ? period.slice(0, 4) : "Loading..."}</strong>
          </div>
          <div className="mapwrap">
            {loadError ? <p style={{ padding: "1rem 1.25rem" }}>{loadError}</p> :
              <MapView city={city} buildings={buildings} selected={selected} onSelect={setSelected} />}
            {selected && <BuildingDrawer id={selected} onClose={() => setSelected(null)} />}
          </div>
          <div className="map-activity-info"><ParkingLegend baselineMethod="mean" /></div>
          {meta && <Stalls periods={meta.periods} index={pi} onChange={setPi} summary={summary} />}
        </section>

        <section id="parallax-chat" className="col chat-column" aria-label="Chat" hidden={!chatOpen}>
          <button className="close-chat" type="button" onClick={() => setChatOpen(false)}>Close chat</button>
          <AgentPanel turns={turns} running={running} onAsk={ask} />
        </section>

        <section className="col results-column" aria-label="Results">
          <button className="chat-launcher" type="button" aria-expanded={chatOpen} aria-controls="parallax-chat" onClick={() => setChatOpen(!chatOpen)}>{chatOpen ? "Hide chat" : "Ask about these results"}</button>
          <ResultsPanel r={results} onPickBin={pickBin} onPickBuilding={pickBuilding} />
        </section>
      </main>
    </div>
  );
}
