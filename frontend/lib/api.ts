export type Meta = {
  data_mode: string;
  agent_mode: "llm" | "scripted";
  cities: string[];
  periods: string[];
  n_buildings: number;
  n_measurable: number;
};

export type Building = {
  id: string;
  name: string;
  city: string;
  submarket: string;
  lat: number;
  lon: number;
  type: string;
  cls: string;
  parking: string;
  index: number | null;
  abs_index: number | null;
  status: string;
};

export type Bin = {
  bin: number;
  usage_min: number;
  usage_max: number;
  usage_median: number;
  n: number;
  renewal_rate: number;
  ci_low: number;
  ci_high: number;
};

export type AgentEvent =
  | { type: "plan"; todos: { content: string; status: string }[] }
  | { type: "step"; agent: string; tool: string; args: Record<string, unknown> }
  | { type: "result"; tool: string; data: any }
  | { type: "note"; text: string }
  | { type: "final"; text: string }
  | { type: "error"; text: string }
  | { type: "done" };

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  meta: () => fetch("/api/meta").then(j<Meta>),
  buildings: (period: string, city?: string) =>
    fetch(`/api/buildings?period=${period}${city ? `&city=${encodeURIComponent(city)}` : ""}`).then(j<Building[]>),
  building: (id: string) => fetch(`/api/buildings/${id}`).then(j<any>),
  overview: () => fetch("/api/results/overview").then(j<any>),
  screen: () => fetch("/api/screen?limit=500").then(j<any>),
  tool: (name: string, args: Record<string, unknown>) =>
    fetch(`/api/tools/${name}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(args),
    }).then(j<any>),
  imageUrl: (id: string, captureId: string) => `/api/buildings/${id}/image?capture_id=${captureId}`,
};

/** POST a question and stream server-sent events back. */
export async function askStream(question: string, onEvent: (e: AgentEvent) => void, signal?: AbortSignal) {
  const r = await fetch("/api/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`ask failed: ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i).trim();
      buf = buf.slice(i + 2);
      if (chunk.startsWith("data:")) {
        try {
          onEvent(JSON.parse(chunk.slice(5).trim()));
        } catch {
          /* ignore partial */
        }
      }
    }
  }
}

/** Usage index -> color. Slate below the building's baseline, ochre above, concrete near 100. */
export function usageColor(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "#B9C0C4";
  const stops: [number, [number, number, number]][] = [
    [50, [44, 86, 132]],
    [80, [96, 136, 176]],
    [100, [203, 207, 205]],
    [120, [222, 170, 60]],
    [150, [176, 112, 22]],
  ];
  const x = Math.max(50, Math.min(150, v));
  for (let k = 1; k < stops.length; k++) {
    const [x1, c1] = stops[k];
    const [x0, c0] = stops[k - 1];
    if (x <= x1) {
      const t = (x - x0) / (x1 - x0);
      const c = c0.map((a, i) => Math.round(a + (c1[i] - a) * t));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }
  }
  return "rgb(176,112,22)";
}

export const pct = (v: number | null | undefined, d = 0) => (v == null ? "n/a" : `${(v * 100).toFixed(d)}%`);
