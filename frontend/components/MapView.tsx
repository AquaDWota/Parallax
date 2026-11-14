"use client";
import { useEffect } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { Building } from "@/lib/api";
import { usageColor } from "@/lib/api";

const CENTERS: Record<string, [number, number, number]> = {
  Houston: [29.82, -95.55, 10],
  "Los Angeles": [34.03, -118.3, 10],
};

function Recenter({ city }: { city: string }) {
  const map = useMap();
  useEffect(() => {
    const c = CENTERS[city];
    if (c) map.setView([c[0], c[1]], c[2]);
  }, [city, map]);
  return null;
}

export default function MapView({ city, buildings, selected, onSelect, watch }: {
  city: string;
  buildings: Building[];
  selected: string | null;
  onSelect: (id: string) => void;
  watch?: Set<string>;
}) {
  const c = CENTERS[city] ?? CENTERS.Houston;
  return (
    <MapContainer center={[c[0], c[1]]} zoom={c[2]} preferCanvas scrollWheelZoom>
      {/* Keyless OpenStreetMap tiles, desaturated in CSS so the usage colors carry the map */}
      <TileLayer
        className="basemap"
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; OpenStreetMap contributors'
        maxZoom={19}
      />
      <Recenter city={city} />
      {buildings.map((b) => {
        const garage = b.parking !== "surface";
        const sel = b.id === selected;
        const onWatch = !!watch?.has(b.id);
        return (
          <CircleMarker
            key={b.id}
            center={[b.lat, b.lon]}
            radius={sel ? 9 : onWatch ? 7 : garage ? 3 : 5}
            pathOptions={{
              color: sel ? "#2b2f33" : onWatch ? "#9b3b2f" : garage ? "#8d969b" : "rgba(43,47,51,0.35)",
              weight: sel ? 3 : onWatch ? 2.5 : 1,
              fillColor: garage ? "transparent" : usageColor(b.abs_index),
              fillOpacity: garage ? 0 : 0.92,
            }}
            eventHandlers={{ click: () => onSelect(b.id) }}
          >
            <Tooltip direction="top" offset={[0, -4]}>
              <strong>{b.name}</strong>
              <br />
              {b.submarket}, {b.type}, Class {b.cls}{onWatch ? " (on the lender watchlist)" : ""}
              <br />
              {garage ? "Garage parking: not measurable from above" :
                b.abs_index == null ? `No usable capture (${b.status.replace("_", " ")})` :
                `Lot ${b.abs_index.toFixed(0)}% as full as before COVID` +
                (b.index != null ? `; ${b.index.toFixed(0)} vs. neighbours` : "")}
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
