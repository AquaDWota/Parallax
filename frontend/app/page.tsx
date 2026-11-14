"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import AgentPanel, { type Turn } from "@/components/AgentPanel";
import BuildingDrawer from "@/components/BuildingDrawer";
import ResultsPanel, { type Results } from "@/components/ResultsPanel";
import Stalls from "@/components/Stalls";
import { api, askStream, usageColor, type AgentEvent, type Building, type Meta } from "@/lib/api";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function Page() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [city, setCity] = useState("Houston");
  const [pi, setPi] = useState(0);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<Results>({});
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api.meta().then((m) => {
      setMeta(m);
      const pre = m.periods.filter((p) => p < "2020");
      setPi(Math.max(0, m.periods.indexOf(pre[pre.length - 1] ?? m.periods[0])));
    })
      .catch(() => setLoadError("Can't reach the API on port 8000. Start it with: cd backend && uvicorn api.main:app --port 8000"));
    api.overview().then((o) => setResults({ bins: o.bins, regression: o.regression, regional: o.regional })).catch(() => {});
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
    return `${m.length} lots measured, median fill ${med.toFixed(0)}% of pre-COVID`;
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
    setResults((r) => ({ regional: r.regional, bins: r.bins, regression: r.regression }));
    setTurns((ts) => [...ts, { question: q, events: [] }]);
    try {
      await askStream(q, onEvent);
    } catch (err) {
      onEvent({ type: "error", text: `The agent stopped: ${String(err)}` });
    } finally {
      setRunning(false);
    }
  }, [onEvent]);

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
    <div className="shell">
      <header className="topbar">
        <h1 className="wordmark">Parallax</h1>
        <p className="thesis">Does an emptying parking lot predict a tenant leaving? Surface-lot buildings in Houston and LA, from Vexcel aerial captures and CoStar tenancies.</p>
        {meta && <span className="mode">{meta.data_mode === "synthetic" ? "Synthetic data" : "Real Vexcel + CoStar data"}, {meta.agent_mode === "llm" ? "LLM planner" : "scripted planner"}</span>}
      </header>

      <main className="grid">
        <section className="col" aria-label="Map">
          <div className="col-head">
            <h2>Lots by usage</h2>
            <div className="citypick" role="group" aria-label="City">
              {(meta?.cities ?? ["Houston", "Los Angeles"]).map((c) => (
                <button key={c} type="button" aria-pressed={c === city} onClick={() => { setCity(c); setSelected(null); }}>{c}</button>
              ))}
            </div>
          </div>
          <div className="mapwrap">
            {loadError ? <p style={{ padding: "1rem 1.25rem" }}>{loadError}</p> :
              <MapView city={city} buildings={buildings} selected={selected} onSelect={setSelected} />}
            <div className="legend" aria-hidden>
              Lot fill, % of its pre-COVID level
              <div className="ramp">{[50, 65, 80, 92, 100, 108, 120, 135, 150].map((v) => <span key={v} style={{ background: usageColor(v) }} />)}</div>
              <div className="ends"><span>50</span><span>100</span><span>150</span></div>
              <div style={{ marginTop: 4, color: "var(--asphalt-2)" }}>Hollow: garage, not measurable</div>
            </div>
            {selected && <BuildingDrawer id={selected} onClose={() => setSelected(null)} />}
          </div>
          {meta && <Stalls periods={meta.periods} index={pi} onChange={setPi} summary={summary} />}
        </section>

        <section className="col" aria-label="Agent">
          <AgentPanel turns={turns} running={running} onAsk={ask} />
        </section>

        <section className="col" aria-label="Results">
          <ResultsPanel r={results} onPickBin={pickBin} onPickBuilding={pickBuilding} />
        </section>
      </main>
    </div>
  );
}
