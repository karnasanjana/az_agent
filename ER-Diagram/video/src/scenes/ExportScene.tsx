import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import { fontFamily } from "../fonts";

// Aligned with PRODUCT_STRATEGY.md Phase 2 features
const features = [
  {
    icon: (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
        <path d="M9 12h6m-3-3v6m-7 4h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    label: "AI Auto-Documentation",
    sub: "Plain-English descriptions for every table and column — generated instantly",
    color: theme.indigo[400],
  },
  {
    icon: (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
        <path d="M13 10V3L4 14h7v7l9-11h-7z" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    label: "Impact Analysis",
    sub: '"If I change customer_id, what breaks?" — see every affected table instantly',
    color: "#f59e0b",
  },
  {
    icon: (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" stroke="#14b8a6" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" stroke="#14b8a6" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    label: "Shareable Links",
    sub: "Send a read-only link to anyone — no login required. This is how it spreads in teams.",
    color: "#14b8a6",
  },
];

export const ExportScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, fps * 0.4], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: theme.bg,
        fontFamily,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 50,
        }}
      >
        {/* Title */}
        <div
          style={{
            opacity: titleOpacity,
            fontSize: 48,
            fontWeight: 800,
            background: `linear-gradient(135deg, ${theme.indigo[400]}, ${theme.accent})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Built for Teams
        </div>

        <div
          style={{
            opacity: titleOpacity,
            fontSize: 20,
            color: theme.muted,
            marginTop: -30,
          }}
        >
          Enterprise-grade features at mid-market pricing
        </div>

        {/* Feature cards */}
        <div style={{ display: "flex", gap: 36 }}>
          {features.map((feat, i) => {
            const cardEntrance = spring({
              frame: frame - fps * 0.6 - i * 10,
              fps,
              config: { damping: 15 },
            });

            return (
              <div
                key={feat.label}
                style={{
                  transform: `scale(${cardEntrance})`,
                  width: 320,
                  padding: "36px 28px",
                  borderRadius: 20,
                  background: theme.surface,
                  border: `1px solid ${theme.border}`,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 18,
                  boxShadow: "0 8px 30px rgba(0,0,0,0.3)",
                  textAlign: "center",
                }}
              >
                {/* Icon */}
                <div
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: 18,
                    background: `${feat.color}12`,
                    border: `1px solid ${feat.color}30`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {feat.icon}
                </div>
                <div
                  style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: theme.foreground,
                  }}
                >
                  {feat.label}
                </div>
                <div
                  style={{
                    fontSize: 14,
                    color: theme.muted,
                    lineHeight: 1.6,
                  }}
                >
                  {feat.sub}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
