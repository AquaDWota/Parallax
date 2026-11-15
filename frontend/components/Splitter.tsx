"use client";
import { useRef } from "react";

/** Draggable divider between two panels. Reports horizontal movement in pixels; arrow keys nudge,
 *  double-click resets. */
export default function Splitter({ onDrag, onReset, label }: { onDrag: (dx: number) => void; onReset: () => void; label: string }) {
  const last = useRef<number | null>(null);
  return (
    <div
      className="splitter"
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      tabIndex={0}
      title="Drag to resize. Double-click to reset."
      onPointerDown={(e) => { last.current = e.clientX; (e.target as HTMLElement).setPointerCapture(e.pointerId); document.body.classList.add("resizing"); }}
      onPointerMove={(e) => { if (last.current == null) return; onDrag(e.clientX - last.current); last.current = e.clientX; }}
      onPointerUp={(e) => { last.current = null; (e.target as HTMLElement).releasePointerCapture(e.pointerId); document.body.classList.remove("resizing"); }}
      onPointerCancel={() => { last.current = null; document.body.classList.remove("resizing"); }}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") { e.preventDefault(); onDrag(-32); }
        if (e.key === "ArrowRight") { e.preventDefault(); onDrag(32); }
        if (e.key === "Home" || e.key === "Enter") { e.preventDefault(); onReset(); }
      }}
    />
  );
}
