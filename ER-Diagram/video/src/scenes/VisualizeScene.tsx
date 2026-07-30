import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
  Easing,
} from "remotion";
import { theme } from "../theme";
import { fontFamily } from "../fonts";

// 4 cloud sources with distinct colors
const CLOUDS = {
  azure: {
    color: "#3b82f6",
    gradient: "linear-gradient(135deg, #2563eb, #3b82f6)",
    pk: "#93c5fd",
    label: "Azure",
  },
  gcp: {
    color: "#14b8a6",
    gradient: "linear-gradient(135deg, #0d9488, #14b8a6)",
    pk: "#5eead4",
    label: "Google",
  },
  aws: {
    color: "#f59e0b",
    gradient: "linear-gradient(135deg, #d97706, #f59e0b)",
    pk: "#fcd34d",
    label: "AWS",
  },
  onprem: {
    color: "#10b981",
    gradient: "linear-gradient(135deg, #059669, #10b981)",
    pk: "#6ee7b7",
    label: "On-Prem",
  },
} as const;

type CloudKey = keyof typeof CLOUDS;

type Col = { name: string; type: string; isPK?: boolean; isFK?: boolean };
type TableDef = {
  name: string;
  columns: Col[];
  x: number;
  y: number;
  delay: number;
  cloud: CloudKey;
  width: number;
};

const ROW_H = 28;
const HEADER_H = 36;

// Wave 1: Azure tables (appear first)
// Wave 2: Google Cloud tables
// Wave 3: AWS tables
// Wave 4: On-Prem tables
const tables: TableDef[] = [
  // Azure — top-left quadrant
  {
    name: "Users", cloud: "azure", width: 220, x: 60, y: 100, delay: 0,
    columns: [
      { name: "id", type: "INT", isPK: true },
      { name: "name", type: "NVARCHAR" },
      { name: "email", type: "NVARCHAR" },
    ],
  },
  {
    name: "Roles", cloud: "azure", width: 200, x: 380, y: 80, delay: 4,
    columns: [
      { name: "id", type: "INT", isPK: true },
      { name: "name", type: "NVARCHAR" },
      { name: "user_id", type: "INT", isFK: true },
    ],
  },
  {
    name: "Sessions", cloud: "azure", width: 210, x: 80, y: 290, delay: 6,
    columns: [
      { name: "id", type: "GUID", isPK: true },
      { name: "user_id", type: "INT", isFK: true },
      { name: "token", type: "VARCHAR" },
    ],
  },
  {
    name: "AuditLog", cloud: "azure", width: 210, x: 400, y: 280, delay: 8,
    columns: [
      { name: "id", type: "BIGINT", isPK: true },
      { name: "user_id", type: "INT", isFK: true },
      { name: "action", type: "VARCHAR" },
    ],
  },

  // Google Cloud — top-right quadrant
  {
    name: "Products", cloud: "gcp", width: 220, x: 960, y: 90, delay: 30,
    columns: [
      { name: "id", type: "STRING", isPK: true },
      { name: "name", type: "STRING" },
      { name: "price", type: "FLOAT64" },
    ],
  },
  {
    name: "Categories", cloud: "gcp", width: 210, x: 1300, y: 80, delay: 34,
    columns: [
      { name: "id", type: "STRING", isPK: true },
      { name: "name", type: "STRING" },
      { name: "parent_id", type: "STRING", isFK: true },
    ],
  },
  {
    name: "Reviews", cloud: "gcp", width: 220, x: 980, y: 280, delay: 36,
    columns: [
      { name: "id", type: "STRING", isPK: true },
      { name: "product_id", type: "STRING", isFK: true },
      { name: "rating", type: "INT64" },
    ],
  },
  {
    name: "Inventory", cloud: "gcp", width: 210, x: 1320, y: 270, delay: 38,
    columns: [
      { name: "id", type: "STRING", isPK: true },
      { name: "product_id", type: "STRING", isFK: true },
      { name: "warehouse", type: "STRING" },
    ],
  },

  // AWS — bottom-left quadrant
  {
    name: "Orders", cloud: "aws", width: 220, x: 60, y: 490, delay: 60,
    columns: [
      { name: "id", type: "uuid", isPK: true },
      { name: "user_id", type: "int", isFK: true },
      { name: "total", type: "numeric" },
    ],
  },
  {
    name: "OrderItems", cloud: "aws", width: 220, x: 380, y: 480, delay: 64,
    columns: [
      { name: "id", type: "uuid", isPK: true },
      { name: "order_id", type: "uuid", isFK: true },
      { name: "product_id", type: "text", isFK: true },
    ],
  },
  {
    name: "Shipping", cloud: "aws", width: 210, x: 80, y: 660, delay: 66,
    columns: [
      { name: "id", type: "uuid", isPK: true },
      { name: "order_id", type: "uuid", isFK: true },
      { name: "carrier", type: "text" },
    ],
  },
  {
    name: "Returns", cloud: "aws", width: 210, x: 400, y: 660, delay: 68,
    columns: [
      { name: "id", type: "uuid", isPK: true },
      { name: "order_id", type: "uuid", isFK: true },
      { name: "reason", type: "text" },
    ],
  },

  // On-Prem — bottom-right quadrant
  {
    name: "Payments", cloud: "onprem", width: 220, x: 960, y: 490, delay: 90,
    columns: [
      { name: "id", type: "SERIAL", isPK: true },
      { name: "order_id", type: "INT", isFK: true },
      { name: "amount", type: "DECIMAL" },
    ],
  },
  {
    name: "Invoices", cloud: "onprem", width: 210, x: 1300, y: 480, delay: 94,
    columns: [
      { name: "id", type: "SERIAL", isPK: true },
      { name: "payment_id", type: "INT", isFK: true },
      { name: "pdf_path", type: "TEXT" },
    ],
  },
  {
    name: "Accounts", cloud: "onprem", width: 220, x: 980, y: 660, delay: 96,
    columns: [
      { name: "id", type: "SERIAL", isPK: true },
      { name: "user_id", type: "INT", isFK: true },
      { name: "balance", type: "DECIMAL" },
    ],
  },
  {
    name: "Ledger", cloud: "onprem", width: 210, x: 1320, y: 660, delay: 98,
    columns: [
      { name: "id", type: "SERIAL", isPK: true },
      { name: "account_id", type: "INT", isFK: true },
      { name: "entry", type: "TEXT" },
    ],
  },
];

function getTableBottom(t: TableDef) {
  return t.y + HEADER_H + t.columns.length * ROW_H;
}

function getEdgePoint(
  t: TableDef,
  tx: number,
  ty: number
): [number, number] {
  const w = t.width;
  const h = HEADER_H + t.columns.length * ROW_H;
  const cx = t.x + w / 2;
  const cy = t.y + h / 2;
  const dx = tx - cx;
  const dy = ty - cy;
  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);
  if (absDx === 0 && absDy === 0) return [cx, cy];
  const scaleX = absDx / (w / 2);
  const scaleY = absDy / (h / 2);
  if (scaleX > scaleY) {
    const side = dx > 0 ? t.x + w : t.x;
    const yAt = cy + (dy / absDx) * (w / 2);
    return [side, Math.max(t.y, Math.min(t.y + h, yAt))];
  } else {
    const side = dy > 0 ? t.y + h : t.y;
    const xAt = cx + (dx / absDy) * (h / 2);
    return [Math.max(t.x, Math.min(t.x + w, xAt)), side];
  }
}

type RelDef = { from: string; to: string; delay: number; label: string };

const relationships: RelDef[] = [
  // Azure internal
  { from: "Users", to: "Roles", delay: 12, label: "user_id" },
  { from: "Users", to: "Sessions", delay: 14, label: "user_id" },
  { from: "Users", to: "AuditLog", delay: 16, label: "user_id" },
  // GCP internal
  { from: "Products", to: "Categories", delay: 42, label: "parent" },
  { from: "Products", to: "Reviews", delay: 44, label: "product_id" },
  { from: "Products", to: "Inventory", delay: 46, label: "product_id" },
  // AWS internal
  { from: "Orders", to: "OrderItems", delay: 72, label: "order_id" },
  { from: "Orders", to: "Shipping", delay: 74, label: "order_id" },
  { from: "Orders", to: "Returns", delay: 76, label: "order_id" },
  // On-Prem internal
  { from: "Payments", to: "Invoices", delay: 102, label: "payment_id" },
  { from: "Accounts", to: "Ledger", delay: 104, label: "account_id" },
  // Cross-cloud relationships (appear last — the magic moment)
  { from: "Users", to: "Orders", delay: 115, label: "user_id" },
  { from: "OrderItems", to: "Products", delay: 120, label: "product_id" },
  { from: "Orders", to: "Payments", delay: 125, label: "order_id" },
  { from: "Users", to: "Accounts", delay: 130, label: "user_id" },
];

const TableNode: React.FC<{ table: TableDef; frame: number; fps: number }> = ({
  table,
  frame,
  fps,
}) => {
  const entrance = spring({
    frame: frame - table.delay,
    fps,
    config: { damping: 15, stiffness: 120 },
  });
  const cloud = CLOUDS[table.cloud];

  return (
    <div
      style={{
        position: "absolute",
        left: table.x,
        top: table.y,
        transform: `scale(${entrance})`,
        transformOrigin: "center center",
        width: table.width,
        borderRadius: 10,
        overflow: "hidden",
        border: `1px solid rgba(255,255,255,0.1)`,
        background: theme.slate[800],
        boxShadow: `0 4px 20px rgba(0,0,0,0.5)`,
      }}
    >
      <div
        style={{
          padding: "8px 12px",
          background: cloud.gradient,
          fontSize: 13,
          fontWeight: 700,
          color: "#fff",
          height: HEADER_H,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span>{table.name}</span>
        <span style={{ fontSize: 9, opacity: 0.75, fontWeight: 500 }}>{cloud.label}</span>
      </div>
      {table.columns.map((col, i) => (
        <div
          key={col.name}
          style={{
            padding: "4px 12px",
            fontSize: 11,
            height: ROW_H,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            color: col.isPK ? cloud.pk : col.isFK ? "#fbbf24" : theme.slate[300],
            fontWeight: col.isPK ? 700 : 400,
            borderBottom: i < table.columns.length - 1 ? `1px solid ${theme.border}` : "none",
            fontFamily: "monospace",
          }}
        >
          <span>
            {col.isPK ? "PK " : col.isFK ? "FK " : "   "}
            {col.name}
          </span>
          <span style={{ fontSize: 9, color: theme.slate[500] }}>{col.type}</span>
        </div>
      ))}
    </div>
  );
};

// Cloud legend item
const CloudBadge: React.FC<{
  cloud: CloudKey;
  frame: number;
  fps: number;
  waveDelay: number;
  x: number;
  y: number;
}> = ({ cloud, frame, fps, waveDelay, x, y }) => {
  const c = CLOUDS[cloud];
  const opacity = interpolate(frame, [waveDelay, waveDelay + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pulseScale = spring({
    frame: frame - waveDelay,
    fps,
    config: { damping: 12 },
  });

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        opacity,
        transform: `scale(${pulseScale})`,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <div
        style={{
          width: 14,
          height: 14,
          borderRadius: 4,
          background: c.color,
          boxShadow: `0 0 8px ${c.color}60`,
        }}
      />
      <span style={{ fontSize: 13, color: theme.slate[300], fontWeight: 600 }}>{c.label}</span>
    </div>
  );
};

export const VisualizeScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, fps * 0.3], [0, 1], {
    extrapolateRight: "clamp",
  });

  // "Add Data Source" button animation (pulses before each wave)
  const wave2Pulse = interpolate(frame, [25, 30, 35], [1, 1.08, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const wave3Pulse = interpolate(frame, [55, 60, 65], [1, 1.08, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const wave4Pulse = interpolate(frame, [85, 90, 95], [1, 1.08, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const addBtnScale = Math.max(wave2Pulse, wave3Pulse, wave4Pulse);
  const addBtnOpacity = interpolate(frame, [fps * 0.3, fps * 0.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Cross-cloud label
  const crossCloudOpacity = interpolate(frame, [112, 118], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: theme.bg, fontFamily }}>
      {/* Grid */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `linear-gradient(${theme.border} 1px, transparent 1px), linear-gradient(90deg, ${theme.border} 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
          opacity: 0.12,
        }}
      />

      {/* Title bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 56,
          background: "rgba(15,23,42,0.8)",
          borderBottom: `1px solid ${theme.border}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 30px",
          opacity: titleOpacity,
        }}
      >
        <div
          style={{
            fontSize: 20,
            fontWeight: 800,
            background: `linear-gradient(135deg, ${theme.indigo[400]}, ${theme.accent})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Instant Schema Understanding
        </div>

        {/* Add Data Source button */}
        <div
          style={{
            opacity: addBtnOpacity,
            transform: `scale(${addBtnScale})`,
            padding: "8px 20px",
            borderRadius: 8,
            background: `linear-gradient(135deg, ${theme.indigo[600]}, ${theme.indigo[500]})`,
            fontSize: 13,
            fontWeight: 600,
            color: "#fff",
            display: "flex",
            alignItems: "center",
            gap: 6,
            boxShadow: `0 0 15px ${theme.indigo[500]}30`,
          }}
        >
          <span style={{ fontSize: 16 }}>+</span> Add Data Source
        </div>
      </div>

      {/* Cloud badges — legend */}
      <CloudBadge cloud="azure" frame={frame} fps={fps} waveDelay={0} x={60} y={68} />
      <CloudBadge cloud="gcp" frame={frame} fps={fps} waveDelay={30} x={940} y={68} />
      <CloudBadge cloud="aws" frame={frame} fps={fps} waveDelay={60} x={60} y={458} />
      <CloudBadge cloud="onprem" frame={frame} fps={fps} waveDelay={90} x={940} y={458} />

      {/* Cross-cloud connections label */}
      <div
        style={{
          position: "absolute",
          bottom: 20,
          width: "100%",
          textAlign: "center",
          opacity: crossCloudOpacity,
          fontSize: 16,
          fontWeight: 600,
          color: "#fbbf24",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M13 10V3L4 14h7v7l9-11h-7z" fill="#fbbf24" />
        </svg>
        Cross-cloud relationships detected
      </div>

      {/* Quadrant dividers */}
      <div
        style={{
          position: "absolute",
          top: 56,
          left: "50%",
          width: 1,
          height: "calc(100% - 56px)",
          background: `linear-gradient(to bottom, transparent, ${theme.border}, ${theme.border}, transparent)`,
          opacity: interpolate(frame, [20, 40], [0, 0.3], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      />
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: 0,
          right: 0,
          height: 1,
          background: `linear-gradient(to right, transparent, ${theme.border}, ${theme.border}, transparent)`,
          opacity: interpolate(frame, [50, 70], [0, 0.3], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      />

      {/* Relationship lines */}
      <svg
        style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%" }}
      >
        <defs>
          <marker id="arr-same" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0, 7 2.5, 0 5" fill={theme.indigo[400]} opacity="0.7" />
          </marker>
          <marker id="arr-cross" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0, 7 2.5, 0 5" fill="#fbbf24" opacity="0.8" />
          </marker>
        </defs>
        {relationships.map((rel, i) => {
          const fromT = tables.find((t) => t.name === rel.from)!;
          const toT = tables.find((t) => t.name === rel.to)!;
          const fromC = CLOUDS[fromT.cloud];
          const toC = CLOUDS[toT.cloud];

          const fCx = fromT.x + fromT.width / 2;
          const fCy = fromT.y + (HEADER_H + fromT.columns.length * ROW_H) / 2;
          const tCx = toT.x + toT.width / 2;
          const tCy = toT.y + (HEADER_H + toT.columns.length * ROW_H) / 2;

          const [x1, y1] = getEdgePoint(fromT, tCx, tCy);
          const [x2, y2] = getEdgePoint(toT, fCx, fCy);

          const progress = interpolate(
            frame,
            [rel.delay, rel.delay + 15],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.quad) }
          );

          const isCross = fromT.cloud !== toT.cloud;
          const strokeColor = isCross ? "#fbbf24" : fromC.color;
          const marker = isCross ? "url(#arr-cross)" : "url(#arr-same)";

          const ex = x1 + (x2 - x1) * progress;
          const ey = y1 + (y2 - y1) * progress;

          // Curved control point
          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;
          const d = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) || 1;
          const off = isCross ? 40 : 25;
          const cpx = mx - ((y2 - y1) / d) * off;
          const cpy = my + ((x2 - x1) / d) * off;

          return (
            <g key={i}>
              <path
                d={`M ${x1} ${y1} Q ${cpx} ${cpy} ${ex} ${ey}`}
                fill="none"
                stroke={strokeColor}
                strokeWidth={isCross ? 2.5 : 1.5}
                opacity={0.7 * progress}
                markerEnd={progress > 0.9 ? marker : undefined}
                strokeDasharray={isCross ? "none" : "none"}
              />
              {progress > 0.85 && (
                <text
                  x={mx}
                  y={my - 8}
                  textAnchor="middle"
                  fontSize={9}
                  fill={isCross ? "#fbbf24" : theme.muted}
                  opacity={interpolate(progress, [0.85, 1], [0, 0.8])}
                  fontFamily="monospace"
                >
                  {rel.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Table nodes */}
      {tables.map((table) => (
        <TableNode key={table.name} table={table} frame={frame} fps={fps} />
      ))}
    </AbsoluteFill>
  );
};
