"use client";
import { useState } from "react";
import type { Bin } from "@/lib/api";
import { pct } from "@/lib/api";
import { BinsChart, LeadChart, RegionalChart } from "./charts";

export type Results = {
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
        {bins?.bins && (
          <section className="result">
            <h3>Renewal rate by parking usage</h3>
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
            <p className="sub">{metric === "usage_index" ? "Average lot fill as % of 2018-19, weighted by building size. Shaded: 2020-21." : "Share of expiring tenants that kept all their space, per half-year."}</p>
            <RegionalChart series={r.regional.series} metric={metric} />
          </section>
        )}
      </div>
    </>
  );
}
