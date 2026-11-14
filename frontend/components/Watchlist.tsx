"use client";
import { useState } from "react";

type Row = {
  rank: number; building_id: string; name: string; city: string; property_type: string; building_class?: string;
  leased_pre: number; leased_now: number; leased_change: number; parking_now: number; gap: number;
  rollover_24m: number; expiring_tenants: string; watch: boolean; data_check: boolean; n_recent: number;
};

const fmt = (v: number | null | undefined, d = 0) => (v == null ? "n/a" : v.toFixed(d));
const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}`;

/** Lender risk screen: leased on paper vs used in the lot. */
export default function Watchlist({ data, onPick }: { data: any; onPick: (id: string) => void }) {
  const [showAll, setShowAll] = useState(false);
  const [showSetAside, setShowSetAside] = useState(false);
  if (!data?.rows) return <p className="sub">Loading the screen.</p>;
  if (!data.rows.length) return <p className="sub">No buildings have both pre-COVID and 2023+ captures yet.</p>;
  const s = data.summary;
  const rows: Row[] = data.rows.filter((r: Row) => (showSetAside ? true : !r.data_check)).filter((r: Row) => (showAll ? true : r.watch));
  return (
    <>
      <section className="result">
        <h3>Leased on paper, empty in the lot</h3>
        <p style={{ margin: "0 0 0.5rem" }}>
          <span className="headline-num">{s.n_watch}</span> of {s.n_clean} buildings are leased within 5 points of
          pre-COVID while their lots run under 70% of pre-COVID.
        </p>
        <p className="sub">
          Across all of them, lots run at {fmt(s.median_parking_now)}% of pre-COVID while CoStar occupancy changed
          {" "}{signed(s.median_leased_change)} points. Leased but unused space is the space most likely to go dark at
          renewal. Gap = how many more points the lot lost than the lease record did. Occupancy is computed from
          CoStar tenancies and is approximate.
        </p>
        <div className="toggle">
          <button type="button" aria-pressed={!showAll} onClick={() => setShowAll(false)}>Watchlist ({s.n_watch})</button>
          <button type="button" aria-pressed={showAll} onClick={() => setShowAll(true)}>All buildings ({showSetAside ? s.n : s.n_clean})</button>
          <button type="button" aria-pressed={showSetAside} onClick={() => setShowSetAside(!showSetAside)}
            title="Buildings whose CoStar tenant history looks incomplete">
            {showSetAside ? "Hide" : "Show"} records to check ({s.n - s.n_clean})
          </button>
        </div>
        <table className="screen">
          <thead>
            <tr>
              <th>Building</th>
              <th className="num">Leased now</th>
              <th className="num">Lot vs pre-COVID</th>
              <th className="num">Gap</th>
              <th className="num">Expiring 24 mo</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.building_id} onClick={() => onPick(r.building_id)} tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter") onPick(r.building_id); }}
                className={r.watch ? "watch" : r.data_check ? "check" : ""}
                title={r.expiring_tenants || undefined}>
                <td>
                  <span className="bname">{r.name}</span>
                  <span className="bmeta">{r.city === "Los Angeles" ? "LA" : r.city}, {r.property_type}{r.building_class && r.building_class !== "U" ? ` ${r.building_class}` : ""}{r.data_check ? ", check records" : ""}</span>
                </td>
                <td className="num">{fmt(r.leased_now)}%<span className="bmeta">{signed(r.leased_change)} pts</span></td>
                <td className="num">{fmt(r.parking_now)}%</td>
                <td className="num strong">{signed(r.gap)}</td>
                <td className="num">{r.rollover_24m ? `${fmt(r.rollover_24m)}%` : "none recorded"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sub" style={{ marginTop: "0.5rem" }}>Click a building to see its lot over time. Hover a row for the tenants whose leases expire.</p>
      </section>
    </>
  );
}
