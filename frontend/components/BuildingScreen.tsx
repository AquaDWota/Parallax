"use client";
import { useEffect, useState } from "react";

type Row = {
  rank: number; building_id: string; name: string; city: string; property_type: string; building_class?: string;
  leased_pre: number; leased_now: number; leased_change: number; parking_now: number; gap: number; opportunity_score: number;
  rollover_24m: number; expiring_tenants: string; watch: boolean; opportunity: boolean; data_check: boolean; n_recent: number;
};
type View = "risk" | "opportunity" | "all";

const fmt = (v: number | null | undefined, d = 0) => (v == null ? "n/a" : v.toFixed(d));
const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}`;

/** Building screen: where the lease record and the parking lot disagree, in either direction. */
export default function BuildingScreen({ data, onPick, shown, focus }: { data: any; onPick: (id: string) => void; shown?: Set<string>; focus?: "risk" | "opportunity" | null }) {
  const [view, setView] = useState<View>(focus ?? "risk");
  useEffect(() => { if (focus) setView(focus); }, [focus]);
  const [showSetAside, setShowSetAside] = useState(false);
  if (!data?.rows) return <p className="sub">Loading the screen.</p>;
  if (!data.rows.length) return <p className="sub">No buildings have both pre-COVID and 2023+ captures yet.</p>;
  const s = data.summary;
  const keep = (r: Row) => (view === "risk" ? r.watch : view === "opportunity" ? r.opportunity : true);
  let rows: Row[] = data.rows.filter((r: Row) => (showSetAside ? true : !r.data_check)).filter(keep);
  if (view === "opportunity") rows = [...rows].sort((a, b) => b.opportunity_score - a.opportunity_score);
  const scoreLabel = view === "opportunity" ? "Investment score" : view === "risk" ? "Risk score" : "Score";
  const score = (r: Row) => (view === "opportunity" ? r.opportunity_score : view === "risk" ? r.gap : r.opportunity && !r.watch ? r.opportunity_score : r.gap);

  return (
    <section className="result">
      <h3>{view === "opportunity" ? "Busier than the leases suggest" : view === "risk" ? "Leased on paper, empty in the lot" : "Every building screened"}</h3>
      {view === "opportunity" ? (
        <p style={{ margin: "0 0 0.5rem" }}>
          <span className="headline-num up">{s.n_opportunity ?? 0}</span> of {s.n_clean} buildings have lots at or above
          their pre-COVID level while leasing is flat or down and there is room left to lease.
        </p>
      ) : (
        <p style={{ margin: "0 0 0.5rem" }}>
          <span className="headline-num down">{s.n_watch}</span> of {s.n_clean} buildings are leased within 5 points of
          pre-COVID while their lots run under 70% of pre-COVID.
        </p>
      )}
      <p className="sub">
        {view === "opportunity"
          ? "A busy lot with space still to lease points to demand the lease record hasn't caught up with: lease-up upside, or tenants CoStar hasn't recorded yet. Investment score = how many more points the lot gained than the leases did."
          : "Leased but unused space is the space most likely to go dark at renewal. Risk = how many more points the lot lost than the lease record did."}
        {" "}Across all buildings, lots run at {fmt(s.median_parking_now)}% of pre-COVID while CoStar occupancy changed
        {" "}{signed(s.median_leased_change)} points. Occupancy is computed from CoStar tenancies and is approximate.
      </p>
      <div className="toggle">
        <button type="button" aria-pressed={view === "risk"} onClick={() => setView("risk")}>Risk ({s.n_watch})</button>
        <button type="button" aria-pressed={view === "opportunity"} onClick={() => setView("opportunity")}>Investment ({s.n_opportunity ?? 0})</button>
        <button type="button" aria-pressed={view === "all"} onClick={() => setView("all")}>All buildings ({showSetAside ? s.n : s.n_clean})</button>
        <button type="button" aria-pressed={showSetAside} onClick={() => setShowSetAside(!showSetAside)}
          title="Buildings whose CoStar tenant history looks incomplete">
          {showSetAside ? "Hide" : "Show"} records to check ({s.n - s.n_clean})
        </button>
      </div>
      {rows.length === 0 ? <p className="sub">No buildings in this view.</p> : (
        <table className="screen">
          <thead>
            <tr>
              <th>Building</th>
              <th className="num">Leased now</th>
              <th className="num">Lot vs pre-COVID</th>
              <th className="num">{scoreLabel}</th>
              <th className="num">Expiring 24 mo</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.building_id} onClick={() => onPick(r.building_id)} tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter") onPick(r.building_id); }}
                className={r.watch ? "watch" : r.opportunity ? "opp" : r.data_check ? "check" : ""}
                title={r.expiring_tenants || undefined}>
                <td>
                  <span className="bname">{r.name}</span>
                  {shown?.has(r.building_id) && <span className="shownTag">shown in answer</span>}
                  <span className="bmeta">{r.city === "Los Angeles" ? "LA" : r.city}, {r.property_type}{r.building_class && r.building_class !== "U" ? ` ${r.building_class}` : ""}{r.data_check ? ", check records" : ""}</span>
                </td>
                <td className="num">{fmt(r.leased_now)}%<span className={`bmeta ${r.leased_change > 0 ? "up" : r.leased_change < 0 ? "down" : ""}`}>{signed(r.leased_change)} pts</span></td>
                <td className={`num ${r.parking_now >= 100 ? "up" : "down"}`}>{fmt(r.parking_now)}%</td>
                <td className={`num strong ${view === "opportunity" || (view === "all" && r.opportunity && !r.watch) ? "up" : r.watch ? "down" : ""}`}>{signed(score(r))}</td>
                <td className="num">{r.rollover_24m ? `${fmt(r.rollover_24m)}%` : "none recorded"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="sub" style={{ marginTop: "0.5rem" }}>Click a building to see its lot over time. Hover a row for the tenants whose leases expire.</p>
    </section>
  );
}
