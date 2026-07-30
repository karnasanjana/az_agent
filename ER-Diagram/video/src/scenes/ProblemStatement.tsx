import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { theme } from "../theme";
import { fontFamily } from "../fonts";

const comparisons = [
  { task: "Understanding a database", before: "2-3 weeks", after: "30 seconds", delay: 0 },
  { task: "Impact analysis before changes", before: "2-3 days", after: "Instant", delay: 1.8 },
  { task: "Audit documentation", before: "$10-50K consultant", after: "Auto-generated", delay: 3.6 },
  { task: "Explaining schema to team", before: "Hours of meetings", after: "Share a link", delay: 5.4 },
];

export const ProblemStatement: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, fps * 0.4], [0, 1], {
    extrapolateRight: "clamp",
  });

  // "What if" reveal
  const revealDelay = fps * 8;
  const revealOpacity = interpolate(
    frame,
    [revealDelay, revealDelay + fps * 0.5],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const revealScale = spring({
    frame: frame - revealDelay,
    fps,
    config: { damping: 12 },
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
      {/* Grid background */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `linear-gradient(${theme.border} 1px, transparent 1px), linear-gradient(90deg, ${theme.border} 1px, transparent 1px)`,
          backgroundSize: "60px 60px",
          opacity: 0.12,
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 32,
          width: "100%",
          maxWidth: 1200,
        }}
      >
        {/* Title */}
        <div
          style={{
            opacity: titleOpacity,
            fontSize: 42,
            fontWeight: 800,
            color: theme.slate[300],
          }}
        >
          The real cost of not understanding your data
        </div>

        {/* Before / After table */}
        <div
          style={{
            width: "100%",
            maxWidth: 1000,
            display: "flex",
            flexDirection: "column",
            gap: 0,
          }}
        >
          {/* Header row */}
          <div
            style={{
              display: "flex",
              opacity: titleOpacity,
              marginBottom: 12,
            }}
          >
            <div style={{ flex: 2, fontSize: 14, fontWeight: 700, color: theme.slate[500], textTransform: "uppercase", letterSpacing: 2 }}>
              Process
            </div>
            <div style={{ flex: 1, fontSize: 14, fontWeight: 700, color: "#ef4444", textTransform: "uppercase", letterSpacing: 2, textAlign: "center" }}>
              Today
            </div>
            <div style={{ flex: 1, fontSize: 14, fontWeight: 700, color: "#10b981", textTransform: "uppercase", letterSpacing: 2, textAlign: "center" }}>
              With DataLake
            </div>
          </div>

          {/* Comparison rows */}
          {comparisons.map((row, i) => {
            const rowDelay = row.delay * fps;
            const rowOpacity = interpolate(
              frame,
              [rowDelay, rowDelay + fps * 0.4],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );
            const rowY = interpolate(
              frame,
              [rowDelay, rowDelay + fps * 0.4],
              [20, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.quad) }
            );

            // "After" column slides in with a delay
            const afterDelay = rowDelay + fps * 0.6;
            const afterScale = spring({
              frame: frame - afterDelay,
              fps,
              config: { damping: 15 },
            });

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  opacity: rowOpacity,
                  transform: `translateY(${rowY}px)`,
                  padding: "18px 24px",
                  borderRadius: 14,
                  background: i % 2 === 0 ? "rgba(255,255,255,0.02)" : "transparent",
                  border: `1px solid ${i % 2 === 0 ? theme.border : "transparent"}`,
                  marginBottom: 8,
                }}
              >
                {/* Task */}
                <div style={{ flex: 2, fontSize: 20, fontWeight: 600, color: theme.foreground }}>
                  {row.task}
                </div>

                {/* Before — red/warning */}
                <div
                  style={{
                    flex: 1,
                    textAlign: "center",
                    fontSize: 20,
                    fontWeight: 700,
                    color: "#f87171",
                    textDecoration: afterScale > 0.5 ? "line-through" : "none",
                    opacity: afterScale > 0.5 ? 0.5 : 1,
                  }}
                >
                  {row.before}
                </div>

                {/* After — green/success */}
                <div
                  style={{
                    flex: 1,
                    textAlign: "center",
                    transform: `scale(${afterScale})`,
                  }}
                >
                  <span
                    style={{
                      fontSize: 20,
                      fontWeight: 800,
                      color: "#10b981",
                      padding: "6px 16px",
                      borderRadius: 8,
                      background: "rgba(16, 185, 129, 0.1)",
                      border: "1px solid rgba(16, 185, 129, 0.2)",
                    }}
                  >
                    {row.after}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* "What if all of this took seconds?" */}
        <div
          style={{
            marginTop: 24,
            opacity: revealOpacity,
            transform: `scale(${revealScale})`,
            fontSize: 44,
            fontWeight: 800,
            textAlign: "center",
          }}
        >
          <span style={{ color: theme.foreground }}>What if all of this took </span>
          <span
            style={{
              background: `linear-gradient(135deg, ${theme.indigo[400]}, ${theme.accent})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            seconds?
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
