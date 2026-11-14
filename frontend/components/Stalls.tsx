"use client";
import { useEffect, useRef, useState } from "react";

const MONTH: Record<string, string> = { "03": "Mar", "09": "Sep" };

/** Capture picker drawn as a row of parking stalls; the selected capture is the occupied stall. */
export default function Stalls({ periods, index, onChange, summary }: {
  periods: string[];
  index: number;
  onChange: (i: number) => void;
  summary: string;
}) {
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const idx = useRef(index);
  idx.current = index;

  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      const next = idx.current + 1;
      if (next >= periods.length) {
        setPlaying(false);
        return;
      }
      onChange(next);
    }, 900);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, periods.length, onChange]);

  const p = periods[index] ?? "";
  const [y, m] = p.split("-");
  const label = (per: string) => (per.length === 4 ? per : `${MONTH[per.slice(5)] ?? ""} ${per.slice(0, 4)}`);
  const isCovid = (per: string) => per.slice(0, 4) === "2020" || per.slice(0, 4) === "2021";

  return (
    <div className="stalls">
      <div className="stall-caption">
        <strong>{m ? `${MONTH[m] ?? m} ${y}` : y}</strong>
        <span>{summary}</span>
        <button
          className="play"
          type="button"
          onClick={() => {
            if (!playing && index >= periods.length - 1) onChange(0);
            setPlaying(!playing);
          }}
        >
          {playing ? "Pause" : `Play ${periods[0]?.slice(0, 4)} to ${periods[periods.length - 1]?.slice(0, 4)}`}
        </button>
      </div>
      <div
        className="stalls-row"
        role="radiogroup"
        aria-label="Aerial capture"
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") onChange(Math.min(periods.length - 1, index + 1));
          if (e.key === "ArrowLeft") onChange(Math.max(0, index - 1));
        }}
      >
        {periods.map((per, i) => {
          const covid = isCovid(per);
          return (
            <button
              key={per}
              type="button"
              className="stall"
              role="radio"
              aria-checked={i === index}
              aria-pressed={i === index}
              aria-label={label(per)}
              tabIndex={i === index ? 0 : -1}
              onClick={() => onChange(i)}
            >
              {covid && <span className="covid" title="2020-21 pandemic period" />}
              <span className="car" />
            </button>
          );
        })}
      </div>
      <div className="stall-labels" aria-hidden>
        {periods.map((per) => (
          <span key={per}>{per.length === 4 || per.endsWith("03") ? `'${per.slice(2, 4)}` : ""}</span>
        ))}
      </div>
    </div>
  );
}
