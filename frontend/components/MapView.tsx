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

export default function MapView({ city, buildings, selected, onSelect }: {
  city: string;
  buildings: Building[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const c = CENTERS[city] ?? CENTERS.Houston;
  return (
    <MapContainer center={[c[0], c[1]]} zoom={c[2]} preferCanvas scrollWheelZoom>
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap contributors &copy; CARTO'
      />
      <TileLayer url="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png" opacity={0.7} />
      <Recenter city={city} />
      {buildings.map((b) => {
        const garage = b.parking !== "surface";
        const sel = b.id === selected;
        return (
          <CircleMarker
            key={b.id}
            center={[b.lat, b.lon]}
            radius={sel ? 9 : garage ? 3 : 5}
            pathOptions={{
              color: sel ? "#2b2f33" : garage ? "#8d969b" : "rgba(43,47,51,0.35)",
              weight: sel ? 3 : 1,
              fillColor: garage ? "transparent" : usageColor(b.abs_index),
              fillOpacity: garage ? 0 : 0.92,
            }}
            eventHandlers={{ click: () => onSelect(b.id) }}
          >
            <Tooltip direction="top" offset={[0, -4]}>
              <strong>{b.name}</strong>
              <br />
              {b.submarket}, {b.type}, Class {b.cls}
              <br />
              {garage ? "Garage parking: not measurable from above" :
                b.abs_index == null ? `No usable capture (${b.status.replace("_", " ")})` :
                `Lot ${b.abs_index.toFixed(0)}% as full as in 2018-19` +
                (b.index != null ? `; ${b.index.toFixed(0)} vs. neighbours` : "")}
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
