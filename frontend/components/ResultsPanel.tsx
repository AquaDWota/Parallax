"use client";
import { useState } from "react";
import type { Bin } from "@/lib/api";
import { pct } from "@/lib/api";
import { BinsChart, LeadChart, OccBinsChart, OffsetChart, RegionalChart } from "./charts";
import Watchlist from "./Watchlist";

export type Results = {
  occLink?: any;
  occLead?: any;
  occDrop?: any;
  occGroups?: any;
  bins?: any;
  regression?: any;
  lead?: any;
  regional?: any;
  groups?: any[];
  validate?: any;
  examples?: any;
};

function sliceLabel(f: Record<string, any> | undefined) {
  if (!f || !Object.keys(f).length) return "All measurable buildings, Houston and LA";
  const p: string[] = [];
  if (f.building_class) p.push(`Class ${f.building_class}`);
  if (f.property_type) p.push(f.property_type);
  if (f.tenant_industry) p.push(`${f.tenant_industry} tenants`);
  if (f.city) p.push(`in ${f.city}`);
  if (f.min_lease_share) p.push(`tenants leasing ${Math.round(f.min_lease_share * 100)}%+ of their building`);
  if (f.exclude_covid) p.push("excluding 2020-21");
  const s = p.join(", ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function ResultsPanel({ r, onPickBin, onPickBuilding, view, setView, screen, shownInAnswer }: {
  r: Results;
  onPickBin: (b: Bin, filters: Record<string, any>) => void;
  onPickBuilding: (id: string) => void;
  shownInAnswer?: Set<string>;
  view: "study" | "watchlist";
  setView: (v: "study" | "watchlist") => void;
  screen: any;
}) {
  const [metric, setMetric] = useState<"usage_index" | "renewal_rate">("usage_index");
  const bins = r.bins;
  const e = bins?.emptiest_vs_busiest;
  const reg = r.regression;

  return (
    <>
      <div className="col-head">
        <h2>{view === "watchlist" ? "Lender watchlist" : "Results"}</h2>
        <div className="viewtabs" role="group" aria-label="Results view">
          <button type="button" aria-pressed={view === "study"} onClick={() => setView("study")}>Study</button>
          <button type="button" aria-pressed={view === "watchlist"} onClick={() => setView("watchlist")}>Watchlist</button>
        </div>
      </div>
      <div className="col-body">
        {view === "watchlist" ? <Watchlist data={screen} onPick={onPickBuilding} shown={shownInAnswer} /> : <>
        {r.occLink?.bins?.length > 0 && (
          <section className="result">
            <h3>Parking tracks occupancy</h3>
            <p className="sub">{sliceLabel(r.occLink.filters)}. {r.occLink.n_buildings} buildings, {r.occLink.n.toLocaleString()} captures.
              Each bar compares a building with itself: lot usage vs its usual level, when CoStar shows it fuller or emptier than usual.</p>
            <p style={{ margin: "0 0 0.5rem" }}>
              <span className="headline-num">{r.occLink.usage_pts_per_10pt_occupancy > 0 ? "+" : ""}{r.occLink.usage_pts_per_10pt_occupancy.toFixed(1)}</span> usage
              points for every 10 points of occupancy, in the same building.
            </p>
            <OccBinsChart bins={r.occLink.bins} />
            <p className="sub" style={{ marginTop: "0.5rem" }}>
              95% CI {r.occLink.ci_low.toFixed(1)} to {r.occLink.ci_high.toFixed(1)}, p={r.occLink.p_value < 0.001 ? "<0.001" : r.occLink.p_value.toFixed(3)}.
              {r.occLink.placebo ? ` Placebo (usage shuffled across buildings): ${r.occLink.placebo.placebo_mean}, ${r.occLink.placebo.passed ? "passed" : "failed"}.` : ""}
            </p>
          </section>
        )}

        {r.occDrop?.n_drops && (
          <section className="result">
            <h3>After a lot empties sharply</h3>
            <p className="sub">Occupancy change by the next capture, for lots that fell more than {Math.abs(r.occDrop.threshold)} points vs all others.</p>
            <table className="groups">
              <tbody>
                <tr><td>Lot fell sharply ({r.occDrop.n_drops})</td><td className="num">{r.occDrop.occ_change_after_drop > 0 ? "+" : ""}{r.occDrop.occ_change_after_drop} pts</td></tr>
                <tr><td>All other captures ({r.occDrop.n_rest})</td><td className="num">{r.occDrop.occ_change_otherwise > 0 ? "+" : ""}{r.occDrop.occ_change_otherwise} pts</td></tr>
                <tr><td>Difference</td><td className="num">{r.occDrop.difference} pts (p={r.occDrop.p_value.toFixed(2)})</td></tr>
              </tbody>
            </table>
          </section>
        )}

        {r.occLead?.offsets && (
          <section className="result">
            <h3>When parking and occupancy line up</h3>
            <p className="sub">Usage points per 10 points of occupancy, with occupancy measured before, at and after the capture. Filled dots: p &lt; 0.1.</p>
            <OffsetChart offsets={r.occLead.offsets} />
          </section>
        )}

        {r.occGroups?.groups && (
          <section className="result">
            <h3>Where it holds: by {r.occGroups.by.replace("_", " ")}</h3>
            <table className="groups">
              <tbody>
                {r.occGroups.groups.filter((x: any) => x.usage_pts_per_10pt_occupancy != null).map((x: any) => (
                  <tr key={x.group}>
                    <td>{x.group}</td>
                    <td className="num">{x.usage_pts_per_10pt_occupancy > 0 ? "+" : ""}{x.usage_pts_per_10pt_occupancy}{x.p_value >= 0.1 ? " (n.s.)" : ""}</td>
                    <td className="num">{x.n_buildings} bldgs</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {bins?.bins && (
          <section className="result">
            <h3>{r.occLink ? "Secondary: renewal rate by parking usage" : "Renewal rate by parking usage"}</h3>
            <p className="sub">{sliceLabel(bins.filters)}. {bins.n.toLocaleString()} lease expiries, 2019-2026. Click a bar for example buildings.</p>
            {e && (
              <p style={{ margin: "0 0 0.5rem" }}>
                <span className="headline-num">{pct(e.emptiest)}</span> of tenants in the emptiest lots renewed,
                against <strong>{pct(e.busiest)}</strong> in the busiest.
              </p>
            )}
            <BinsChart bins={bins.bins} onPick={(b) => onPickBin(b, bins.filters ?? {})} />
            {reg?.interpretation && (
              <p className="sub" style={{ marginTop: "0.5rem" }}>
                {reg.interpretation} n={reg.n.toLocaleString()}, p={reg.p_value_usage < 0.001 ? "<0.001" : reg.p_value_usage.toFixed(3)}.
              </p>
            )}
          </section>
        )}

        {r.examples?.examples?.length > 0 && (
          <section className="result">
            <h3>Example buildings</h3>
            <p className="sub">{r.examples.which === "busiest" ? "Busiest lots before expiry" :
              r.examples.usage_bin ? `Usage bin ${r.examples.usage_bin}` : "Emptiest lots before expiry"}. Open one to see the lot then and now.</p>
            <div className="examples">
              {r.examples.examples.map((x: any) => (
                <button key={x.building_id + x.expiry} className="example" type="button" onClick={() => onPickBuilding(x.building_id)}>
                  <span className="who">{x.tenant}</span>
                  <span className="outcome" data-o={x.outcome}>{x.outcome.replace("_", " ")}</span>
                  <span className="meta">
                    {x.name}, {x.submarket}. {Math.round(x.lease_share * 100)}% of the building, expired {x.expiry}.
                    Usage before expiry {x.usage_before_expiry}.
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {r.lead?.leads && (
          <section className="result">
            <h3>How far ahead the signal works</h3>
            <p className="sub">Odds of renewal per 10-point usage drop (below 1 means less likely to renew), measured at each window before expiry, with out-of-sample AUC.</p>
            <LeadChart leads={r.lead.leads} />
          </section>
        )}

        {r.groups?.map((g, gi) => (
          <section className="result" key={gi}>
            <h3>Where it holds: by {g.by.replace("_", " ")}</h3>
            <p className="sub">Odds of renewal per 10-point usage drop. Lower means a stronger link.</p>
            <table className="groups">
              <tbody>
                {g.groups.map((x: any) => (
                  <tr key={x.group}>
                    <td>{x.group}</td>
                    <td className="num">{x.odds_ratio_per_10pt_drop?.toFixed(2) ?? "n/a"}{x.p_value_usage != null && x.p_value_usage >= 0.05 ? " (n.s.)" : ""}</td>
                    <td className="num">n={x.n?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}

        {r.validate && (
          <section className="result">
            <h3>Validation</h3>
            <table className="groups">
              <tbody>
                {r.validate.out_of_sample?.auc_with_usage != null && (
                  <tr><td>Out of sample, 2023-26 (AUC)</td><td className="num">{r.validate.out_of_sample.auc_baseline} to {r.validate.out_of_sample.auc_with_usage}</td></tr>
                )}
                {r.validate.placebo && (
                  <tr><td>Placebo: usage shuffled within submarket</td><td className="num">OR {r.validate.placebo.placebo_mean_odds_ratio} ({r.validate.placebo.passed ? "passed" : "failed"})</td></tr>
                )}
                {r.validate.covid?.without_2020_2021?.odds_ratio_per_10pt_drop && (
                  <tr><td>Without 2020-21 expiries</td><td className="num">OR {r.validate.covid.without_2020_2021.odds_ratio_per_10pt_drop}</td></tr>
                )}
                {r.validate.detector_noise_15pct?.odds_ratio_per_10pt_drop && (
                  <tr><td>Car counts with ±15% noise</td><td className="num">OR {r.validate.detector_noise_15pct.odds_ratio_per_10pt_drop}</td></tr>
                )}
              </tbody>
            </table>
          </section>
        )}

        {r.regional?.series && (
          <section className="result">
            <h3>Houston and LA, 2018-2026</h3>
            <div className="toggle">
              <button type="button" aria-pressed={metric === "usage_index"} onClick={() => setMetric("usage_index")}>Parking usage</button>
              <button type="button" aria-pressed={metric === "renewal_rate"} onClick={() => setMetric("renewal_rate")}>Renewal rate</button>
            </div>
            <p className="sub">{metric === "usage_index" ? "Average lot fill as % of pre-COVID, weighted by building size. Shaded: 2020-21." : "Share of expiring tenants that kept all their space, per half-year."}</p>
            <RegionalChart series={r.regional.series} metric={metric} />
          </section>
        )}
      </>}
      </div>
    </>
  );
}
