import {
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  staticFile,
  Img,
} from "remotion";
import { theme } from "../theme";
import { fontFamily } from "../fonts";

export const Avatar: React.FC<{ isSpeaking?: boolean }> = ({ isSpeaking = true }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Entrance animation
  const entrance = spring({
    frame,
    fps,
    config: { damping: 15 },
  });

  // Subtle idle breathing
  const breathe = interpolate(
    Math.sin(frame * 0.06),
    [-1, 1],
    [0.98, 1.02]
  );

  // Speaking glow ring pulse
  const glowPulse = isSpeaking
    ? interpolate(Math.sin(frame * 0.3), [-1, 1], [0.4, 0.9])
    : 0.15;

  const glowScale = isSpeaking
    ? interpolate(Math.sin(frame * 0.3), [-1, 1], [1.0, 1.06])
    : 1.0;

  // Speaking indicator dot
  const dotPulse = isSpeaking
    ? interpolate(Math.sin(frame * 0.4), [-1, 1], [0.6, 1])
    : 0.3;

  return (
    <div
      style={{
        transform: `scale(${entrance})`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
        fontFamily,
      }}
    >
      {/* Outer glow ring */}
      <div
        style={{
          position: "relative",
          width: 140,
          height: 140,
        }}
      >
        {/* Glow ring */}
        <div
          style={{
            position: "absolute",
            inset: -4,
            borderRadius: "50%",
            background: `conic-gradient(from ${frame * 2}deg, ${theme.indigo[500]}, ${theme.accent}, ${theme.indigo[500]})`,
            opacity: glowPulse,
            transform: `scale(${glowScale})`,
            filter: "blur(3px)",
          }}
        />

        {/* Avatar image container */}
        <div
          style={{
            position: "absolute",
            inset: 3,
            borderRadius: "50%",
            overflow: "hidden",
            border: `3px solid ${theme.slate[800]}`,
            transform: `scale(${breathe})`,
            boxShadow: `0 4px 20px rgba(0,0,0,0.5)`,
          }}
        >
          <Img
            src={staticFile("avatar.png")}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        </div>

        {/* Speaking indicator dot */}
        <div
          style={{
            position: "absolute",
            bottom: 6,
            right: 6,
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: isSpeaking ? "#10b981" : theme.slate[500],
            border: `3px solid ${theme.slate[800]}`,
            opacity: dotPulse,
            boxShadow: isSpeaking ? "0 0 10px rgba(16,185,129,0.5)" : "none",
          }}
        />
      </div>

      {/* Name label */}
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: theme.slate[300],
          letterSpacing: 1,
          textTransform: "uppercase",
          textAlign: "center",
          background: "rgba(11, 14, 20, 0.7)",
          padding: "4px 12px",
          borderRadius: 6,
          backdropFilter: "blur(8px)",
        }}
      >
        Presenter
      </div>
    </div>
  );
};
