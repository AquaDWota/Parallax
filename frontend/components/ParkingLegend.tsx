"use client";
import { useId, useState } from "react";
import { usageColor } from "@/lib/api";

export default function ParkingLegend({ baselineMethod }: { baselineMethod: "mean" | "median" }) {
  const id = useId();
  const [selected, setSelected] = useState(100);
  const multiple = selected / 100;
  const comparison = selected === 100 ? "At this building's reference level" : `${Math.abs(100-selected)}% ${selected < 100 ? "less" : "more"} activity than this building's reference`;
  return <div className="legend compact-parking-legend" aria-label="Parking activity color scale">
    <strong className="legend-title">Parking activity</strong>
    <div className="ramp" role="group" aria-label="Explore parking activity levels">
      {[50,65,80,92,100,108,120,135,150].map(value => <button key={value} type="button" style={{background: usageColor(value)}} aria-label={`${value/100}x reference activity`} aria-describedby={id} onMouseEnter={()=>setSelected(value)} onFocus={()=>setSelected(value)} onClick={()=>setSelected(value)} />)}
    </div>
    <div className="ends" aria-hidden="true"><span>0.5x</span><span>1x</span><span>1.5x</span></div>
    <div id={id} role="tooltip" className="parking-legend-tooltip">
      <strong>{multiple}x: {comparison}</strong>
      <p>1x = the {baselineMethod} of usable pre-COVID observations for this building (Jan 2016-Feb 2020 in real mode; 2018-2019 in synthetic mode).</p>
      <p>Blue: lower activity. Amber: higher activity. These are not good/bad ratings or the percentage of spaces filled.</p>
      <p>Gray: no usable value. Hollow circle: garage, not measurable. End colors also cover values below 0.5x or above 1.5x.</p>
    </div>
  </div>;
}
