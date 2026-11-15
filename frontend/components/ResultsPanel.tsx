"use client";
import { useState } from "react";
import ParkingGuide from "./ParkingGuide";
import OccupancyExplorer from "./OccupancyExplorer";
import type { Bin } from "@/lib/api";
import { pct, activityMultiple } from "@/lib/api";
import { BinsChart, LeadChart, OccBinsChart, OffsetChart, RegionalChart } from "./charts";

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

export default function ResultsPanel({ r, onPickBin, onPickBuilding }: {
  r: Results;
  onPickBin: (b: Bin, filters: Record<string, any>) => void;
  onPickBuilding: (id: string) => void;
}) {
  const [metric, setMetric] = useState<"usage_index" | "renewal_rate">("usage_index");
  const bins = r.bins;
  const e = bins?.emptiest_vs_busiest;
  const reg = r.regression;

  return (
    <>
      <div className="col-head"><h2>Results</h2></div>
      <div className="col-body">
        <ParkingGuide baselineMethod="mean" />
        <OccupancyExplorer />
        {r.occLink?.bins?.length > 0 && (
          <section className="result">
            <h3>Parking and occupied space</h3>
            <p className="sub">{r.occLink.n_buildings} buildings - {r.occLink.n.toLocaleString()} photos. {sliceLabel(r.occLink.filters)}.</p>
            <p className="result-takeaway">
              {r.occLink.ci_low <= 0 && r.occLink.ci_high >= 0
                ? "The estimated relationship is uncertain."
                : r.occLink.usage_pts_per_10pt_occupancy > 0
                  ? "More occupied space is associated with higher parking activity."
                  : "More occupied space is associated with lower parking activity."}
            </p>
            <div className="simple-example" role="group" aria-label="Illustration of the estimated association">
              <div><span>Occupied space</span><strong>60% to 70%</strong><small>10 percentage points higher</small></div>
              <div><span>Relative parking activity</span><strong>1x to {activityMultiple(100 + r.occLink.usage_pts_per_10pt_occupancy)}</strong><small>1x = pre-COVID reference</small></div>
            </div>
            <p className="sub">Illustration of the model estimate, not a forecast. Multiples show relative activity, not cars or the percentage of spaces filled.</p>
            <p className="result-statistics">
              Estimated change: {r.occLink.usage_pts_per_10pt_occupancy > 0 ? "+" : ""}{activityMultiple(r.occLink.usage_pts_per_10pt_occupancy)} of the reference activity.
              {" "}95% CI: {activityMultiple(r.occLink.ci_low, 4)} to {activityMultiple(r.occLink.ci_high, 4)}.
              {" "}p {r.occLink.p_value < 0.001 ? "< 0.001" : `= ${r.occLink.p_value.toFixed(3)}`}.
            </p>
            <details className="result-details">
              <summary>View chart and calculation details</summary>
              <p className="sub">The model compares each building with itself and adjusts for year. Bars compare parking and occupancy with that building&apos;s study average (mean). Zero means average. A change of +0.1x is one tenth of the pre-COVID reference activity, not 10% above the study average. Whiskers show 95% intervals.</p>
              <OccBinsChart bins={r.occLink.bins} />
              {r.occLink.placebo && <p className="sub">Shuffled-data check: {r.occLink.placebo.passed ? "passed" : "did not pass"}. Shuffled estimate: {activityMultiple(r.occLink.placebo.placebo_mean)}.</p>}
            </details>
          </section>
        )}

        {r.occDrop?.n_drops && (
          <section className="result">
            <h3>After a large drop in parking activity</h3>
            <p className="sub">Relative parking activity fell by more than {activityMultiple(Math.abs(r.occDrop.threshold))} of its reference between two photos. Example: 1x to {activityMultiple(100 - Math.abs(r.occDrop.threshold) - 1)}.</p>
            <p className="sub"><strong>Large does not mean fast.</strong> Photos can be months or years apart.</p>
            <table className="groups">
              <caption className="simple-caption">Average change in occupied space by the following photo</caption>
              <tbody>
                <tr><td>After large drops ({r.occDrop.n_drops} comparisons)</td><td className="num">{r.occDrop.occ_change_after_drop > 0 ? "+" : ""}{r.occDrop.occ_change_after_drop} percentage points</td></tr>
                <tr><td>After other changes ({r.occDrop.n_rest})</td><td className="num">{r.occDrop.occ_change_otherwise > 0 ? "+" : ""}{r.occDrop.occ_change_otherwise} percentage points</td></tr>
                <tr><td>Difference between groups</td><td className="num">{r.occDrop.difference} percentage points</td></tr>
              </tbody>
            </table>
            <p className="result-statistics">p = {r.occDrop.p_value.toFixed(3)}. Observed comparison, not proof that parking changes caused occupancy changes.</p>
          </section>
        )}

        {r.occLead?.offsets && (
          <section className="result">
            <h3>Does timing matter?</h3>
            <p className="sub">Estimated change in relative parking activity for 10 percentage points more occupied space, measured before or after the photo. Whiskers show 95% intervals; filled dots have p &lt; 0.1.</p>
            <OffsetChart offsets={r.occLead.offsets} />
          </section>
        )}

        {r.occGroups?.groups && (
          <section className="result">
            <h3>Comparison by {r.occGroups.by.replace("_", " ")}</h3>
            <table className="groups">
              <tbody>
                {r.occGroups.groups.filter((x: any) => x.usage_pts_per_10pt_occupancy != null).map((x: any) => (
                  <tr key={x.group}>
                    <td>{x.group}</td>
                    <td className="num">{x.usage_pts_per_10pt_occupancy > 0 ? "+" : ""}{activityMultiple(x.usage_pts_per_10pt_occupancy)}{x.p_value >= 0.1 ? " (n.s.)" : ""}</td>
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
                <span className="headline-num">{pct(e.emptiest)}</span> kept or expanded their space in the lowest-activity group,
                against <strong>{pct(e.busiest)}</strong> in the highest-activity group.
              </p>
            )}
            <BinsChart bins={bins.bins} onPick={(b) => onPickBin(b, bins.filters ?? {})} />
            {reg?.interpretation && (
              <p className="sub" style={{ marginTop: "0.5rem" }}>
                {reg.interpretation.replace("Each 10-point drop in parking usage", "Each 0.1x decrease in relative parking activity")} n={reg.n.toLocaleString()}, p={reg.p_value_usage < 0.001 ? "<0.001" : reg.p_value_usage.toFixed(3)}.
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
                    Relative activity before expiry: {activityMultiple(x.usage_before_expiry)}.
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
            <h3>Comparison by {g.by.replace("_", " ")}</h3>
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
                  <tr><td>Car counts with +/-15% noise</td><td className="num">OR {r.validate.detector_noise_15pct.odds_ratio_per_10pt_drop}</td></tr>
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
            <p className="sub">{metric === "usage_index" ? "Parking activity as a multiple of its pre-COVID reference, weighted by building size. Shaded: 2020-21." : "Share of expiring tenants that kept all their space, per half-year."}</p>
            <RegionalChart series={r.regional.series} metric={metric} />
          </section>
        )}
      </div>
    </>
  );
}
