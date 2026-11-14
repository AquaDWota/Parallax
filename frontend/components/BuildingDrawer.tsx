"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Spark } from "./charts";

export default function BuildingDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const [b, setB] = useState<any>(null);
  useEffect(() => {
    setB(null);
    api.building(id).then(setB).catch(() => setB({ error: true }));
  }, [id]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  if (!b) return <div className="drawer"><p>Loading building</p></div>;
  if (b.error) return <div className="drawer"><button className="close" onClick={onClose}>Close</button><p>Couldn't load this building.</p></div>;

  const ok = b.history.filter((h: any) => h.status === "ok");
  const then = ok.find((h: any) => h.date < "2020-01-01") ?? ok[0];
  // "now": the capture just before the most recent move-out, else the latest capture
  const lastExit = [...b.leases].reverse().find((l: any) => (l.outcome === "moved_out" || l.outcome === "downsized") && l.expiry <= (ok[ok.length - 1]?.date ?? ""));
  const now = (lastExit && [...ok].reverse().find((h: any) => h.date < lastExit.expiry)) ?? ok[ok.length - 1];
  const garage = b.parking_type !== "surface";

  return (
    <div className="drawer" role="dialog" aria-label={b.name}>
      <button className="close" type="button" onClick={onClose}>Close</button>
      <h3>{b.name}</h3>
      <p className="facts">
        {b.submarket}, {b.city}. {b.property_type}, Class {b.building_class}, {Math.round(b.sqft).toLocaleString()} sq ft, built {b.year_built}.
        {garage ? " Garage parking: not measurable from above." : ` About ${b.stall_capacity} surface stalls.`}
      </p>

      {!garage && then && now && (
        <div className="thenNow">
          <figure>
            <img src={api.imageUrl(b.building_id, then.capture_id)} alt={`Lot in ${then.date}, ${then.cars} cars`} />
            <figcaption>{then.date}: {then.cars} cars, usage {then.index ?? "n/a"}</figcaption>
          </figure>
          <figure>
            <img src={api.imageUrl(b.building_id, now.capture_id)} alt={`Lot in ${now.date}, ${now.cars} cars`} />
            <figcaption>{now.date}: {now.cars} cars, usage {now.index ?? "n/a"}{lastExit ? `, before ${lastExit.tenant} left` : ""}</figcaption>
          </figure>
        </div>
      )}

      {!garage && <Spark history={b.history} leases={b.leases} />}
      {!garage && <p className="sub">Usage vs. neighbours as % of the pre-COVID level. Red lines: a tenant left or shrank. Blue: renewed.</p>}

      <table className="leases">
        <thead><tr><th>Tenant</th><th>Sq ft</th><th>Expiry</th><th>Outcome</th></tr></thead>
        <tbody>
          {b.leases.filter((l: any) => l.expiry >= "2018-01-01").map((l: any, i: number) => (
            <tr key={i}>
              <td>{l.tenant}<br /><span style={{ color: "var(--asphalt-2)" }}>{l.industry}</span></td>
              <td>{l.sqft.toLocaleString()}</td>
              <td>{l.expiry}</td>
              <td><span className="outcome" data-o={l.outcome}>{l.outcome.replace("_", " ")}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
