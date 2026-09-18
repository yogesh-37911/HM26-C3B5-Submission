import { MapContainer, TileLayer, CircleMarker, Marker, Popup, useMap, useMapEvents } from "react-leaflet";
import { useEffect } from "react";
import L from "leaflet";
import type { MapMarker } from "../../lib/types";

// Leaflet's default marker icons reference image files that Vite doesn't
// bundle by default; point them at the CDN copies rather than fighting the
// bundler over asset URLs for a single-icon MVP need.
const pinIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

const RISK_COLOR: Record<string, string> = {
  HIGH: "#B3452C",
  MODERATE: "#B7841F",
  LOW: "#3F6E52",
};

// Mysuru's approximate centre - used as the default map view.
const MYSURU_CENTER: [number, number] = [12.3052, 76.6552];

function FitBounds({ markers }: { markers: MapMarker[] }) {
  const map = useMap();
  useEffect(() => {
    if (!markers.length) return;
    const bounds = markers.map((m) => [m.lat, m.lng] as [number, number]);
    map.fitBounds(bounds, { padding: [32, 32], maxZoom: 15 });
  }, [markers, map]);
  return null;
}

function ClickToPlace({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

/** Single-pin picker: click anywhere on the map to move the pin. */
export function LocationPicker({
  lat,
  lng,
  onChange,
  height = 280,
}: {
  lat: number;
  lng: number;
  onChange: (lat: number, lng: number) => void;
  height?: number;
}) {
  return (
    <div style={{ height }} className="rounded-lg overflow-hidden border border-[var(--color-line-strong)]">
      <MapContainer center={[lat, lng]} zoom={15} scrollWheelZoom style={{ height: "100%" }}>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickToPlace onPick={onChange} />
        <Marker position={[lat, lng]} icon={pinIcon} />
      </MapContainer>
    </div>
  );
}

export function ComplaintMap({
  markers,
  height = 420,
  onSelect,
}: {
  markers: MapMarker[];
  height?: number;
  onSelect?: (m: MapMarker) => void;
}) {
  return (
    <div style={{ height }} className="rounded-lg overflow-hidden border border-[var(--color-line-strong)]">
      <MapContainer center={MYSURU_CENTER} zoom={13} scrollWheelZoom style={{ height: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {markers.length > 0 && <FitBounds markers={markers} />}
        {markers.map((m) => (
          <CircleMarker
            key={m.public_id}
            center={[m.lat, m.lng]}
            radius={m.priority_level === "CRITICAL" ? 9 : m.priority_level === "HIGH" ? 7 : 5}
            pathOptions={{
              color: RISK_COLOR[m.risk_level] || "#4A5049",
              fillColor: RISK_COLOR[m.risk_level] || "#4A5049",
              fillOpacity: 0.65,
              weight: 1.5,
            }}
            eventHandlers={onSelect ? { click: () => onSelect(m) } : undefined}
          >
            <Popup>
              <div className="text-sm font-sans">
                <p className="font-semibold font-[family-name:var(--font-mono)]">{m.public_id}</p>
                <p>{m.category_name}</p>
                <p className="text-xs text-[var(--color-ink-soft)]">
                  {m.jurisdiction || "Unrouted"} &middot; {m.status.replace("_", " ")}
                </p>
                <p className="text-xs mt-1">
                  Risk {m.risk_level} ({Math.round(m.risk_score)}) &middot; Priority {m.priority_level}
                </p>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
