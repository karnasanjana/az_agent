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

const cloudProviders = [
  {
    name: "Azure",
    subtitle: "SQL Database, Cosmos DB",
    color: "#3b82f6",
    icon: "Az",
    delay: 0,
    selectAt: 2, // seconds when it gets "clicked"
  },
  {
    name: "Google Cloud",
    subtitle: "BigQuery, Cloud SQL",
    color: "#14b8a6",
    icon: "GC",
    delay: 8,
    selectAt: 3,
  },
  {
    name: "AWS",
    subtitle: "RDS, Redshift, DynamoDB",
    color: "#f59e0b",
    icon: "AW",
    delay: 16,
    selectAt: 4,
  },
  {
    name: "On-Premises",
    subtitle: "SQL Server, PostgreSQL",
    color: "#10b981",
    icon: "OP",
    delay: 24,
    selectAt: 5,
  },
];

export const ConnectScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title entrance
  const titleOpacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [0, fps * 0.5], [-30, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: theme.bg,
        justifyContent: "center",
        alignItems: "center",
        fontFamily,
      }}
    >
      {/* Background glows */}
      {cloudProviders.map((p) => {
        const glowOpacity = interpolate(
          frame,
          [p.selectAt * fps, p.selectAt * fps + 10],
          [0, 0.15],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
        return (
          <div
            key={p.name + "-glow"}
            style={{
              position: "absolute",
              width: 300,
              height: 300,
              borderRadius: "50%",
              background: `radial-gradient(circle, ${p.color}, transparent 70%)`,
              filter: "blur(80px)",
              opacity: glowOpacity,
              top: "40%",
              left: `${20 + cloudProviders.indexOf(p) * 20}%`,
            }}
          />
        );
      })}

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
            transform: `translateY(${titleY}px)`,
            fontSize: 52,
            fontWeight: 800,
            background: `linear-gradient(135deg, ${theme.indigo[400]}, ${theme.accent})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Connect to Any Cloud
        </div>

        {/* Subtitle */}
        <div
          style={{
            opacity: titleOpacity,
            fontSize: 22,
            color: theme.muted,
            marginTop: -30,
          }}
        >
          Unify schemas from multiple data sources in one view
        </div>

        {/* Cloud provider cards */}
        <div style={{ display: "flex", gap: 32 }}>
          {cloudProviders.map((provider) => {
            const cardScale = spring({
              frame: frame - fps * 0.6 - provider.delay,
              fps,
              config: { damping: 12 },
            });

            // "Click" animation
            const clickFrame = provider.selectAt * fps;
            const isClicked = frame >= clickFrame;
            const clickPulse = spring({
              frame: frame - clickFrame,
              fps,
              config: { damping: 8, stiffness: 200 },
            });
            const clickScale = isClicked
              ? interpolate(clickPulse, [0, 0.5, 1], [1, 0.92, 1])
              : 1;

            // Checkmark appears after click
            const checkOpacity = interpolate(
              frame,
              [clickFrame + 8, clickFrame + 15],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );

            // Border glow after selection
            const borderGlow = isClicked
              ? interpolate(
                  frame,
                  [clickFrame, clickFrame + 15],
                  [0, 1],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
                )
              : 0;

            return (
              <div
                key={provider.name}
                style={{
                  transform: `scale(${cardScale * clickScale})`,
                  width: 240,
                  padding: "40px 28px",
                  borderRadius: 20,
                  background: isClicked
                    ? `linear-gradient(135deg, ${provider.color}12, ${theme.bg})`
                    : theme.surface,
                  border: `1.5px solid ${isClicked ? `${provider.color}${Math.round(borderGlow * 128).toString(16).padStart(2, "0")}` : "rgba(255,255,255,0.08)"}`,
                  boxShadow: isClicked
                    ? `0 0 30px ${provider.color}20, 0 8px 24px rgba(0,0,0,0.3)`
                    : "0 4px 16px rgba(0,0,0,0.2)",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 16,
                  position: "relative",
                }}
              >
                {/* Checkmark badge */}
                {isClicked && (
                  <div
                    style={{
                      position: "absolute",
                      top: -8,
                      right: -8,
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      background: provider.color,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      opacity: checkOpacity,
                      transform: `scale(${checkOpacity})`,
                      boxShadow: `0 0 12px ${provider.color}60`,
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M5 13l4 4L19 7"
                        stroke="white"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                )}

                {/* Icon */}
                <div
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: 18,
                    background: isClicked ? `${provider.color}20` : theme.slate[800],
                    border: `1px solid ${isClicked ? `${provider.color}50` : theme.slate[700]}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 24,
                    fontWeight: 800,
                    color: isClicked ? provider.color : theme.slate[400],
                    fontFamily: "monospace",
                  }}
                >
                  {provider.icon}
                </div>
                <div
                  style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: isClicked ? provider.color : theme.slate[200],
                  }}
                >
                  {provider.name}
                </div>
                <div style={{ fontSize: 13, color: theme.slate[500], textAlign: "center" }}>
                  {provider.subtitle}
                </div>

                {/* Connected label */}
                {isClicked && (
                  <div
                    style={{
                      opacity: checkOpacity,
                      fontSize: 11,
                      fontWeight: 600,
                      color: provider.color,
                      letterSpacing: 1,
                      textTransform: "uppercase",
                    }}
                  >
                    Connected
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
