"use client";
import { useEffect, useRef, useState } from "react";
import type { Layout, Settings, TextSize, Theme } from "@/lib/settings";

type Option<T> = { value: T; label: string };
const THEMES: Option<Theme>[] = [{ value: "dark", label: "Dark" }, { value: "light", label: "Light" }, { value: "system", label: "System" }];
const LAYOUTS: Option<Layout>[] = [{ value: "results-middle", label: "Results in the middle" }, { value: "agent-middle", label: "Agent in the middle" }];
const SIZES: Option<TextSize>[] = [{ value: "s", label: "Small" }, { value: "m", label: "Medium" }, { value: "l", label: "Large" }];

function Group<T extends string>({ label, options, value, onChange }: { label: string; options: Option<T>[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="setting">
      <span className="setting-label" id={`set-${label}`}>{label}</span>
      <div className="seg" role="group" aria-labelledby={`set-${label}`}>
        {options.map((o) => (
          <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>{o.label}</button>
        ))}
      </div>
    </div>
  );
}

export default function SettingsMenu({ settings, onChange }: { settings: Settings; onChange: (s: Settings) => void }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onClick = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onClick); };
  }, [open]);

  const set = <K extends keyof Settings>(k: K) => (v: Settings[K]) => onChange({ ...settings, [k]: v });

  return (
    <div className="settings" ref={wrap}>
      <button type="button" className="settings-btn" aria-expanded={open} aria-controls="display-settings" onClick={() => setOpen((o) => !o)}>
        Display
      </button>
      {open && (
        <div className="settings-pop" id="display-settings" role="dialog" aria-label="Display settings">
          <Group label="Theme" options={THEMES} value={settings.theme} onChange={set("theme")} />
          <Group label="Panels" options={LAYOUTS} value={settings.layout} onChange={set("layout")} />
          <Group label="Text size" options={SIZES} value={settings.text} onChange={set("text")} />
        </div>
      )}
    </div>
  );
}
