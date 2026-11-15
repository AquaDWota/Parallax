"use client";
import { useEffect, useMemo, useState } from "react";

type Point = { building_id: string; name: string; city: string; date: string; capture_id: string; cars: number; fill_pct: number | null; occupancy_raw: number; occupancy: number; relative_activity: number | null; quality_flag: string; flagged: boolean; image_url?: string };
type Data = { commit: string; scope: string; points: Point[]; mismatches: Point[]; mismatch_rule: string };
const BLUE = "#356e99", AMBER = "#b56b42";
const width = 720, height = 330, left = 62, right = 22, top = 24, bottom = 52;
function quantile(values: number[], q: number) { const sorted = [...values].sort((a,b) => a-b); if (!sorted.length) return 0; const at = (sorted.length-1)*q, lo=Math.floor(at); return sorted[lo] + (sorted[Math.ceil(at)]-sorted[lo])*(at-lo); }
function Series({ points, field, label, color }: { points: Point[]; field: "cars" | "occupancy"; label: string; color: string }) {
  const first = Math.min(...points.map(p=>Date.parse(p.date))), last = Math.max(...points.map(p=>Date.parse(p.date)));
  const max = field === "occupancy" ? 120 : Math.max(1,...points.map(p=>p.cars));
  const x = (p: Point) => left + (Date.parse(p.date)-first)/Math.max(1,last-first)*(width-left-right);
  const y = (v: number) => top + (1-v/max)*(height-top-bottom);
  return <svg className="chart occupancy-series" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
    {[0,.5,1].map(f=><g key={f}><line x1={left} x2={width-right} y1={y(f*max)} y2={y(f*max)} stroke="#d5dfe5"/><text x={left-8} y={y(f*max)+4} textAnchor="end">{Math.round(f*max)}{field==="occupancy"?"%":""}</text></g>)}
    <polyline points={points.map(p=>`${x(p)},${y(p[field])}`).join(" ")} stroke={color} fill="none" strokeWidth="2"/>
    {points.map((p,i)=><circle key={p.capture_id+i} cx={x(p)} cy={y(p[field])} r={4} fill={p.flagged?AMBER:color}><title>{p.date}: {p[field].toFixed(1)}; {p.quality_flag}; {p.name}</title></circle>)}
    <text x={left} y={height-15}>{points[0]?.date}</text><text x={width-right} y={height-15} textAnchor="end">{points[points.length-1]?.date}</text>
    <text x={left} y={16} fontWeight="600">{label}</text>
  </svg>;
}
export default function OccupancyExplorer() {
  const [data,setData]=useState<Data|null>(null),[error,setError]=useState("");
  const [tab,setTab]=useState("scatter"),[city,setCity]=useState("Both cities"),[flagged,setFlagged]=useState(false),[building,setBuilding]=useState(""),[log,setLog]=useState(true),[bands,setBands]=useState("cars");
  useEffect(()=>{fetch("/occupancy-visuals.json").then(r=>{if(!r.ok) throw Error("Plot snapshot is unavailable. Run the local diagnostics exporter.");return r.json();}).then(setData).catch(e=>setError(String(e.message)));},[]);
  const points=useMemo(()=>data?.points.filter(p=>(city==="Both cities"||p.city===city)&&(flagged||!p.flagged))??[],[data,city,flagged]);
  const buildings=useMemo(()=>Array.from(new Map(points.map(p=>[p.building_id,{id:p.building_id,name:p.name,city:p.city}])).values()).sort((a,b)=>a.name.localeCompare(b.name)),[points]);
  const selected=buildings.some(b=>b.id===building)?building:buildings[0]?.id;
  const timeline=points.filter(p=>p.building_id===selected).sort((a,b)=>a.date.localeCompare(b.date));
  const bandLabels=bands==="cars"?["0 cars","1-5 cars","6-20 cars","21-50 cars","51+ cars"]:["0-0.5x","0.5-0.85x","0.85-1.15x","Above 1.15x"];
  const bandRows=bandLabels.map((label,index)=>{const group=points.filter(p=>{
    if(bands==="cars"){const i=p.cars===0?0:p.cars<=5?1:p.cars<=20?2:p.cars<=50?3:4;return i===index;}
    if(p.relative_activity==null)return false;const v=p.relative_activity;return (v<=.5?0:v<=.85?1:v<=1.15?2:3)===index;
  }); const values=group.map(p=>p.occupancy);return {label,n:group.length,buildings:new Set(group.map(p=>p.building_id)).size,min:quantile(values,0),q1:quantile(values,.25),median:quantile(values,.5),q3:quantile(values,.75),max:quantile(values,1)};});
  const zero=points.filter(p=>p.cars===0), highZero=zero.filter(p=>p.occupancy>=80);
  const maxCars=Math.max(1,...points.map(p=>p.cars));
  const x=(cars:number)=>left+(log?Math.log1p(cars)/Math.log1p(maxCars):cars/maxCars)*(width-left-right);
  const y=(occ:number)=>top+(1-occ/120)*(height-top-bottom);
  const ticks=Array.from(new Set([0,1,5,20,100,500,1000,maxCars].filter(v=>v<=maxCars))).sort((a,b)=>a-b);
  return <section className="result occupancy-explorer">
    <h3>Explore cars and recorded occupancy</h3>
    <p className="sub">Compare observations, not prediction accuracy. Snapshot: {data?.commit.slice(0,7)??"loading"}.</p>
    <div className="explorer-tabs" role="tablist" aria-label="Occupancy visualizations">{[["scatter","Cars vs occupancy"],["timeline","Building timeline"],["distribution","Occupancy by parking"],["images","Mismatch examples"]].map(([key,label])=><button key={key} id={`occupancy-tab-${key}`} role="tab" aria-selected={tab===key} aria-controls="occupancy-view" type="button" onClick={()=>setTab(key)}>{label}</button>)}</div>
    {error?<p role="alert">{error}</p>:!data?<p>Loading observations...</p>:<>
    <div className="explorer-controls"><label>City <select value={city} onChange={e=>setCity(e.target.value)}>{["Both cities","Houston","Los Angeles"].map(c=><option key={c}>{c}</option>)}</select></label><label><input type="checkbox" checked={flagged} disabled={tab==="images"} onChange={e=>setFlagged(e.target.checked)}/> Include flagged records</label></div>
    <p className="explorer-count">{points.length.toLocaleString()} photo observations / {buildings.length} buildings. Scatter colors: blue = Houston; orange = Los Angeles. Flagged records include suspicious counts or occupancy above 100%.</p>
    <div role="tabpanel" id="occupancy-view" aria-labelledby={`occupancy-tab-${tab}`}>
    {tab==="scatter"&&<>
      <label className="explorer-check"><input type="checkbox" checked={log} onChange={e=>setLog(e.target.checked)}/> Compress large car counts (log scale; zero is retained)</label>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Detected car count versus recorded occupancy; each dot is one building photo">
        {[0,20,40,60,80,100,120].map(t=><g key={t}><line x1={left} x2={width-right} y1={y(t)} y2={y(t)} stroke={t===100?"#9eabb5":"#e2e8ec"}/><text x={left-8} y={y(t)+4} textAnchor="end">{t}%</text></g>)}
        {ticks.map(t=><text key={t} x={x(t)} y={height-bottom+20} textAnchor="middle">{Math.round(t)}</text>)}
        {points.map((p,i)=><circle key={p.building_id+p.capture_id+i} cx={x(p.cars)} cy={y(p.occupancy)} r={p.cars===0?4:3} fill={p.city==="Houston"?BLUE:AMBER} fillOpacity={p.flagged ? 0.22 : 0.45} stroke={p.flagged?"#8f3f32":"none"}><title>{p.name}, {p.city}, {p.date}: {p.cars} cars; recorded occupancy {p.occupancy.toFixed(1)}% (raw {p.occupancy_raw.toFixed(1)}%); {p.quality_flag}</title></circle>)}
        <text x={width/2} y={height-7} textAnchor="middle">Detected cars{log?" (log-spaced counts)":""}</text><text x={left} y={15}>Recorded occupancy (capped at 120%)</text>
      </svg>
      <p className="metric-example">Of {zero.length} zero-car observations shown, {highZero.length} have recorded occupancy of at least 80%. This is a mismatch count, not a model accuracy score.</p>
      <p className="sub">Building size, photo timing and repeated captures affect this comparison. A dot at 0 cars is not proof of vacancy. Hover over a dot for its source values.</p>
    </>}
    {tab==="timeline"&&<>
      <label className="explorer-select">Building <select value={selected??""} onChange={e=>setBuilding(e.target.value)}>{buildings.map(b=><option key={b.id} value={b.id}>{b.name} ({b.city})</option>)}</select></label>
      {timeline.length?<><Series points={timeline} field="cars" label="Detected cars" color={BLUE}/><Series points={timeline} field="occupancy" label="Recorded occupied space" color={AMBER}/></>:<p>No observations match these filters.</p>}
      <p className="sub">Aligned dates, separate vertical scales. Lines connect occasional photos; gaps are not continuously observed. Orange markers in a timeline denote flagged records.</p>
    </>}
    {tab==="distribution"&&<>
      <label className="explorer-select">Group observations by <select value={bands} onChange={e=>setBands(e.target.value)}><option value="cars">Detected car count</option><option value="relative">Activity relative to reference</option></select></label>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Recorded occupancy distributions by parking group; boxes show the middle half, horizontal line is median">
        {[0,40,80,120].map(t=><g key={t}><line x1={left} x2={width-right} y1={y(t)} y2={y(t)} stroke="#d5dfe5"/><text x={left-8} y={y(t)+4} textAnchor="end">{t}%</text></g>)}
        {bandRows.map((row,i)=>{const cx=left+(i+.5)*(width-left-right)/bandRows.length;return <g key={row.label}>{row.n>0&&<><line x1={cx} x2={cx} y1={y(row.min)} y2={y(row.max)} stroke={BLUE}/><rect x={cx-24} y={y(row.q3)} width={48} height={Math.max(1,y(row.q1)-y(row.q3))} fill="#d5e5ef" stroke={BLUE}/><line x1={cx-24} x2={cx+24} y1={y(row.median)} y2={y(row.median)} stroke="#223e52" strokeWidth="3"/></>}<text x={cx} y={height-bottom+20} textAnchor="middle">{row.label}</text><text x={cx} y={height-bottom+36} textAnchor="middle">n={row.n}</text></g>;})}
      </svg>
      <p className="sub">Box: middle 50%. Line: median. Whiskers: full range, not a confidence interval. Car-count groups mix buildings of different sizes.</p>
      <div className="explorer-table"><table className="groups"><thead><tr><th>Parking group</th><th>Photos</th><th>Buildings</th><th>Median occupancy</th></tr></thead><tbody>{bandRows.map(r=><tr key={r.label}><td>{r.label}</td><td>{r.n}</td><td>{r.buildings}</td><td>{r.n?r.median.toFixed(1)+"%":"No data"}</td></tr>)}</tbody></table></div>
    </>}
    {tab==="images"&&<>
      <p className="sub">Selected examples: at least 80% recorded occupancy, at most 0.5x reference parking activity, from 2023 onward. These are not a random sample or evidence of prediction accuracy. Examples are selected separately and may include flagged records.</p>
      <div className="mismatch-grid">{data.mismatches.filter(p=>city==="Both cities"||p.city===city).map(p=><article className="mismatch-card" key={p.building_id}><h4>{p.name}</h4><p>{p.city} / {p.date}</p><img src={p.image_url} alt={`Actual aerial crop for ${p.name}; existing lot outline`} loading="lazy" onError={e=>{e.currentTarget.hidden=true;}}/><dl><div><dt>Recorded occupancy</dt><dd>{p.occupancy.toFixed(1)}%</dd></div><div><dt>Detected cars</dt><dd>{p.cars}</dd></div><div><dt>Relative activity</dt><dd>{p.relative_activity?.toFixed(2)}x</dd></div></dl><p className="sub">Count quality: {p.quality_flag.replace(/_/g," ")}. Boundary, timing and count accuracy require review.</p></article>)}</div>
      {!data.mismatches.some(p=>city==="Both cities"||p.city===city)&&<p>No examples in this city met the declared selection rule. The threshold has not been relaxed.</p>}
      <p className="sub">Actual image crops only; no simulated fallback. Existing lot geometry and historical counts are retained. A low-parking/high-occupancy case may reflect underuse or measurement/source problems.</p>
    </>}
    </div></>}
  </section>;
}
