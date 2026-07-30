import {
  useCurrentFrame,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import { fontFamily } from "../fonts";

type SubtitleEntry = {
  text: string;
  startFrame: number;
  endFrame: number;
};

export const SubtitleBar: React.FC<{ subtitles: SubtitleEntry[] }> = ({ subtitles }) => {
  const frame = useCurrentFrame();

  const current = subtitles.find(
    (s) => frame >= s.startFrame && frame < s.endFrame
  );

  if (!current) return null;

  // Simple fade in / fade out — no typewriter
  const fadeIn = interpolate(
    frame,
    [current.startFrame, current.startFrame + 10],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const fadeOut = interpolate(
    frame,
    [current.endFrame - 10, current.endFrame],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 40,
        left: 200,
        right: 60,
        opacity,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          padding: "14px 28px",
          borderRadius: 12,
          background: "rgba(11, 14, 20, 0.85)",
          backdropFilter: "blur(12px)",
          border: `1px solid ${theme.border}`,
          fontSize: 18,
          fontWeight: 500,
          color: theme.foreground,
          fontFamily,
          lineHeight: 1.5,
          maxWidth: 900,
          textAlign: "center",
          boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
        }}
      >
        {current.text}
      </div>
    </div>
  );
};
