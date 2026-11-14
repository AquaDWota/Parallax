"use client";
import type { Bin } from "@/lib/api";
import { usageColor } from "@/lib/api";

const W = 420;

/** Renewal rate per usage quintile, CI whiskers. Bars carry the map's usage colors. */
export function BinsChart({ bins, onPick }: { bins: Bin[]; onPick?: (b: Bin) => void }) {
  const H = 200, top = 16, bottom = 44, left = 34;
  const ih = H - top - bottom;
  const max = Math.max(0.8, ...bins.map((b) => b.ci_high));
  const min = Math.min(0.3, ...bins.map((b) => b.ci_low)) - 0.05;
  const y = (v: number) => top + ih * (1 - (v - min) / (max - min));
  const bw = (W - left) / bins.length;
  const ticks = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8].filter((t) => t >= min && t <= max);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={`Renewal rate by usage level: ${bins.map((b) => `${Math.round(b.renewal_rate * 100)}%`).join(", ")}`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={left} x2={W} y1={y(t)} y2={y(t)} stroke="#d5dadc" />
          <text x={left - 6} y={y(t) + 4} textAnchor="end">{Math.round(t * 100)}%</text>
        </g>
      ))}
      {bins.map((b, i) => {
        const x = left + i * bw + bw * 0.18;
        const w = bw * 0.64;
        return (
          <g key={b.bin} className="bar" tabIndex={onPick ? 0 : -1} role={onPick ? "button" : undefined}
            aria-label={`Usage ${b.usage_min}-${b.usage_max}: ${Math.round(b.renewal_rate * 100)}% renewed, n=${b.n}. Show examples.`}
            onClick={() => onPick?.(b)} onKeyDown={(e) => { if (e.key === "Enter") onPick?.(b); }}>
            <rect className="fill" x={x} y={y(b.renewal_rate)} width={w} height={y(min) - y(b.renewal_rate)}
              fill={usageColor(b.usage_median)} stroke="#2b2f33" strokeOpacity={0.25} />
            <line x1={x + w / 2} x2={x + w / 2} y1={y(b.ci_low)} y2={y(b.ci_high)} stroke="#2b2f33" strokeWidth={1.5} />
            <line x1={x + w / 2 - 5} x2={x + w / 2 + 5} y1={y(b.ci_high)} y2={y(b.ci_high)} stroke="#2b2f33" strokeWidth={1.5} />
            <line x1={x + w / 2 - 5} x2={x + w / 2 + 5} y1={y(b.ci_low)} y2={y(b.ci_low)} stroke="#2b2f33" strokeWidth={1.5} />
            <text x={x + w / 2} y={y(b.ci_high) - 5} textAnchor="middle" style={{ fill: "#2b2f33", fontWeight: 600 }}>
              {Math.round(b.renewal_rate * 100)}%
            </text>
            <text x={x + w / 2} y={H - bottom + 16} textAnchor="middle">{Math.round(b.usage_median)}</text>
          </g>
        );
      })}
      <text x={left + (W - left) / 2} y={H - 6} textAnchor="middle">
        Parking usage before expiry (median, % of pre-COVID level)
      </text>
    </svg>
  );
}

/** Odds ratio per 10-point drop, by how far before expiry usage is measured. */
export function LeadChart({ leads }: { leads: { lead_months: number; window: string; odds_ratio_per_10pt_drop: number | null; or_ci_low: number | null; or_ci_high: number | null; oos_auc: number | null }[] }) {
  const H = 170, top = 14, bottom = 40, left = 40;
  const rows = leads.filter((l) => l.odds_ratio_per_10pt_drop != null);
  if (!rows.length) return null;
  const lo = Math.min(0.75, ...rows.map((r) => r.or_ci_low ?? 1));
  const hi = Math.max(1.05, ...rows.map((r) => r.or_ci_high ?? 1));
  const y = (v: number) => top + (H - top - bottom) * ((v - lo) / (hi - lo));
  const step = (W - left) / rows.length;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Odds ratio of renewal per 10-point usage drop, by lead time">
      <line x1={left} x2={W} y1={y(1)} y2={y(1)} stroke="#a7afb4" strokeDasharray="4 3" />
      <text x={left - 6} y={y(1) + 4} textAnchor="end">1.0</text>
      <text x={left - 6} y={y(lo) + 10} textAnchor="end">{lo.toFixed(2)}</text>
      {rows.map((r, i) => {
        const cx = left + step * (i + 0.5);
        return (
          <g key={r.lead_months}>
            <line x1={cx} x2={cx} y1={y(r.or_ci_low!)} y2={y(r.or_ci_high!)} stroke="#2b2f33" strokeWidth={1.5} />
            <circle cx={cx} cy={y(r.odds_ratio_per_10pt_drop!)} r={5} fill="#f2c230" stroke="#2b2f33" strokeWidth={1.5} />
            <text x={cx + 9} y={y(r.odds_ratio_per_10pt_drop!) + 4}>{r.odds_ratio_per_10pt_drop!.toFixed(2)}</text>
            <text x={cx} y={H - bottom + 16} textAnchor="middle">{r.lead_months}-{r.lead_months + 12} mo</text>
            {r.oos_auc != null && <text x={cx} y={H - bottom + 30} textAnchor="middle">AUC {r.oos_auc.toFixed(2)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

type SeriesRow = { city: string; half_year: string; usage_index: number | null; renewal_rate: number | null };

/** Houston vs LA: usage index per half-year. */
export function RegionalChart({ series, metric }: { series: SeriesRow[]; metric: "usage_index" | "renewal_rate" }) {
  const H = 190, top = 12, bottom = 34, left = 36;
  const halves = Array.from(new Set(series.map((s) => s.half_year))).sort();
  const cities = Array.from(new Set(series.map((s) => s.city)));
  const vals = series.map((s) => s[metric]).filter((v): v is number => v != null);
  if (!vals.length) return null;
  const lo = Math.min(...vals) * 0.95, hi = Math.max(...vals) * 1.03;
  const x = (h: string) => left + ((W - left - 70) * halves.indexOf(h)) / Math.max(1, halves.length - 1);
  const y = (v: number) => top + (H - top - bottom) * (1 - (v - lo) / (hi - lo));
  const style: Record<string, { stroke: string; dash?: string }> = {
    Houston: { stroke: "#2b2f33" },
    "Los Angeles": { stroke: "#c4861c", dash: "6 3" },
  };
  const fmt = (v: number) => (metric === "usage_index" ? v.toFixed(0) : `${Math.round(v * 100)}%`);
  const covidX0 = halves.includes("2020-H1") ? x("2020-H1") : null;
  const covidX1 = halves.includes("2021-H2") ? x("2021-H2") : null;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Houston vs LA ${metric.replace("_", " ")} 2018-2026`}>
      {covidX0 != null && covidX1 != null && (
        <rect x={covidX0} y={top} width={covidX1 - covidX0} height={H - top - bottom} fill="#3f6e9a" opacity={0.08} />
      )}
      {metric === "usage_index" && lo < 100 && hi > 100 && (
        <>
          <line x1={left} x2={W - 70} y1={y(100)} y2={y(100)} stroke="#a7afb4" strokeDasharray="4 3" />
          <text x={left - 6} y={y(100) + 4} textAnchor="end">100</text>
        </>
      )}
      {cities.map((c) => {
        const pts = halves
          .map((h) => series.find((s) => s.city === c && s.half_year === h))
          .filter((s): s is SeriesRow => !!s && s[metric] != null);
        if (!pts.length) return null;
        const last = pts[pts.length - 1];
        return (
          <g key={c}>
            <polyline fill="none" stroke={style[c]?.stroke ?? "#3f6e9a"} strokeWidth={2} strokeDasharray={style[c]?.dash}
              points={pts.map((p) => `${x(p.half_year)},${y(p[metric]!)}`).join(" ")} />
            <text x={x(last.half_year) + 6} y={y(last[metric]!) + 4} style={{ fill: style[c]?.stroke, fontWeight: 600 }}>
              {c === "Los Angeles" ? "LA" : c} {fmt(last[metric]!)}
            </text>
          </g>
        );
      })}
      {halves.filter((h) => h.endsWith("H1")).map((h) => (
        <text key={h} x={x(h)} y={H - bottom + 16} textAnchor="middle">{h.slice(0, 4)}</text>
      ))}
    </svg>
  );
}

/** One building's usage history with lease expiries marked. */
export function Spark({ history, leases }: {
  history: { date: string; index: number | null }[];
  leases: { expiry: string; outcome: string; tenant: string }[];
}) {
  const H = 130, top = 10, bottom = 22, left = 30;
  const pts = history.filter((h) => h.index != null);
  if (!pts.length) return <p className="sub">No measurable captures for this building.</p>;
  const t = (d: string) => new Date(d).getTime();
  const t0 = t(history[0].date), t1 = t(history[history.length - 1].date);
  const vals = pts.map((p) => p.index!);
  const lo = Math.min(60, ...vals), hi = Math.max(130, ...vals);
  const x = (d: string) => left + ((W - left - 8) * (t(d) - t0)) / (t1 - t0 || 1);
  const y = (v: number) => top + (H - top - bottom) * (1 - (v - lo) / (hi - lo));
  const exp = leases.filter((l) => t(l.expiry) >= t0 && t(l.expiry) <= t1);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Usage history">
      <line x1={left} x2={W} y1={y(100)} y2={y(100)} stroke="#a7afb4" strokeDasharray="4 3" />
      <text x={left - 5} y={y(100) + 4} textAnchor="end">100</text>
      {exp.map((l, i) => (
        <g key={i}>
          <line x1={x(l.expiry)} x2={x(l.expiry)} y1={top} y2={H - bottom}
            stroke={l.outcome === "moved_out" || l.outcome === "downsized" ? "#9b3b2f" : "#3f6e9a"} strokeWidth={1.2} opacity={0.7}>
          </line>
          <title>{`${l.tenant}: ${l.outcome.replace("_", " ")} (${l.expiry})`}</title>
        </g>
      ))}
      <polyline fill="none" stroke="#2b2f33" strokeWidth={2} points={pts.map((p) => `${x(p.date)},${y(p.index!)}`).join(" ")} />
      {pts.map((p) => <circle key={p.date} cx={x(p.date)} cy={y(p.index!)} r={2.6} fill={usageColor(p.index)} stroke="#2b2f33" strokeWidth={0.8} />)}
      {["2018", "2020", "2022", "2024", "2026"].map((yr) => {
        const d = `${yr}-01-01`;
        if (t(d) < t0 || t(d) > t1) return null;
        return <text key={yr} x={x(d)} y={H - 6} textAnchor="middle">{yr}</text>;
      })}
    </svg>
  );
}
