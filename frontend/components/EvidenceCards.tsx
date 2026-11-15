"use client";
import { useEffect, useState } from "react";
import { api, type AgentEvent } from "@/lib/api";

/** One building the agent named, with what CoStar records say next to what the lot photos show. */
export type Evidence = {
  building_id: string;
  name: string;
  property_type?: string;
  submarket?: string;
  leased_pre?: number | null;   // CoStar occupancy before COVID, %
  leased_now?: number | null;   // CoStar occupancy now, %
  leased_change?: number | null; // points, now vs pre-COVID
  parking_now?: number | null;  // lot since 2023 as % of its pre-COVID fill
  rollover_24m?: number | null; // % of leased sq ft expiring in the next 24 months
  watch?: boolean;
  note?: string;                // free text when the source isn't the screen
};

const MAX_CARDS = 3;

/** Pull the buildings worth showing out of one answer's tool results.
 *  fullScreen: every row of the lender screen (the page loads it for the Watchlist). When the answer used
 *  the screen, cards choose from all of it with the same filters, not just the few rows the agent asked for. */
export function evidenceFrom(events: AgentEvent[], fullScreen?: any[]): Evidence[] {
  const out: Evidence[] = [];
  const seen = new Set<string>();
  const add = (e: Evidence) => {
    if (!e.building_id || seen.has(e.building_id) || out.length >= MAX_CARDS) return;
    seen.add(e.building_id);
    out.push(e);
  };
  for (const e of events) {
    if (e.type !== "result") continue;
    if (e.tool === "shadow_vacancy_screen") {
      // Clearest cases first: CoStar leasing barely moved (within 5 points) while the lot emptied - "leased
      // the same, lot empty" needs no argument. Then the rest of the watchlist, then everything else.
      // Never a row the screen itself flags as a data problem.
      const f = e.data?.filters ?? {};
      const same = (r: any) => (!f.city || String(r.city).toLowerCase() === String(f.city).toLowerCase())
        && (!f.property_type || String(r.property_type).toLowerCase() === String(f.property_type).toLowerCase());
      const pool: any[] = fullScreen?.length ? fullScreen.filter(same) : (e.data?.rows ?? []);
      const rows: any[] = pool.filter((r: any) => !r.data_check);
      const steady = (r: any) => r.watch && Math.abs(r.leased_change ?? 99) <= 5;
      const byGap = (a: any, b: any) => (b.gap ?? 0) - (a.gap ?? 0);
      for (const r of [...rows.filter(steady).sort(byGap), ...rows.filter((r) => r.watch), ...rows]) add(r);
    } else if (e.tool === "example_buildings") {
      for (const x of e.data?.examples ?? [])
        add({
          building_id: x.building_id, name: x.name, property_type: x.property_type, submarket: x.submarket,
          note: `${x.tenant} (${Math.round(x.lease_share * 100)}% of the building), lease ended ${x.expiry}: ${String(x.outcome).replace("_", " ")}.`,
        });
    }
  }
  return out;
}

const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${Math.round(Math.min(v, 100))}%`);

function Card({ e, onPick }: { e: Evidence; onPick: (id: string) => void }) {
  const [b, setB] = useState<any>(null);
  useEffect(() => {
    let live = true;
    api.building(e.building_id).then((x) => live && setB(x)).catch(() => live && setB({ error: true }));
    return () => { live = false; };
  }, [e.building_id]);

  const ok: any[] = b?.history?.filter((h: any) => h.status === "ok" && h.cars != null) ?? [];
  const then = ok.find((h) => h.date < "2020-03-01") ?? ok[0];
  const now = ok[ok.length - 1];
  const photos = then && now && then.capture_id !== now.capture_id;

  return (
    <article className="evidence" aria-label={`Evidence for ${e.name}`}>
      <header>
        <h4>{e.name}</h4>
        <span className="sub">{[e.property_type, e.submarket].filter(Boolean).join(" · ")}</span>
        {e.watch && <span className="flag">leased on paper, empty in the lot</span>}
      </header>

      <div className="photos">
        {photos ? (
          <>
            <figure>
              <img loading="lazy" src={api.imageUrl(e.building_id, then.capture_id)} alt={`Lot on ${then.date}: ${then.cars} cars`} />
              <figcaption>{then.date.slice(0, 4)} · {then.cars} cars</figcaption>
            </figure>
            <span className="arrow" aria-hidden>→</span>
            <figure>
              <img loading="lazy" src={api.imageUrl(e.building_id, now.capture_id)} alt={`Lot on ${now.date}: ${now.cars} cars`} />
              <figcaption>{now.date.slice(0, 4)} · {now.cars} cars</figcaption>
            </figure>
          </>
        ) : (
          <p className="nophoto">{b ? "Not enough usable lot photos to compare." : "Loading lot photos…"}</p>
        )}
      </div>

      {e.leased_now != null || e.parking_now != null ? (
        <dl className="says">
          <div><dt>CoStar says</dt><dd>{pct(e.leased_pre)} → <b>{pct(e.leased_now)}</b> leased</dd></div>
          <div><dt>The lot says</dt><dd><b>{e.parking_now == null ? "n/a" : `${Math.round(e.parking_now)}%`}</b> of its pre-COVID cars</dd></div>
          {!!e.rollover_24m && e.rollover_24m > 0 && (
            <div className="warn"><dt>Expiring in 24 months</dt><dd><b>{Math.round(e.rollover_24m)}%</b> of leased space</dd></div>
          )}
        </dl>
      ) : e.note ? <p className="says">{e.note}</p> : null}

      <div className="actions">
        <button type="button" onClick={() => onPick(e.building_id)}>Show on map</button>
        {b?.tour_url && <a href={b.tour_url} target="_blank" rel="noreferrer">Walk through it (3D tour) ↗</a>}
      </div>
    </article>
  );
}

/** How many buildings the screen put on the watchlist in this answer (for the "see all" link). */
export function watchCountFrom(events: AgentEvent[]): number {
  let n = 0;
  for (const e of events) if (e.type === "result" && e.tool === "shadow_vacancy_screen") n = Math.max(n, e.data?.summary?.n_watch ?? 0);
  return n;
}

export default function EvidenceCards({ items, onPick, nWatch = 0, onSeeAll }: {
  items: Evidence[];
  onPick: (id: string) => void;
  nWatch?: number;
  onSeeAll?: () => void;
}) {
  if (!items.length) return null;
  return (
    <section className="evidenceList" aria-label="Evidence">
      <p className="kicker">{items.some((e) => e.leased_change != null && Math.abs(e.leased_change) <= 5 && e.watch)
        ? "Clearest cases: leasing unchanged, lot emptied" : "Evidence: records vs. the lot"}</p>
      {items.map((e) => <Card key={e.building_id} e={e} onPick={onPick} />)}
      {onSeeAll && nWatch > items.length && (
        <button type="button" className="seeAll" onClick={onSeeAll}>See all {nWatch} on the Watchlist →</button>
      )}
    </section>
  );
}
