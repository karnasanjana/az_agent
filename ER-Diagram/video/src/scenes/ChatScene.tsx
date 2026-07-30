import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../theme";
import { fontFamily } from "../fonts";

// Framed as ONBOARDING, not optimization (per PRODUCT_STRATEGY.md)
const chatMessages = [
  {
    role: "user" as const,
    text: "What does this database do?",
    delay: 0,
  },
  {
    role: "ai" as const,
    text: "This is an e-commerce platform database spanning 4 cloud providers. It manages user authentication (Azure), product catalog (Google Cloud), order fulfillment (AWS), and financial transactions (On-Prem).",
    delay: 25,
  },
  {
    role: "user" as const,
    text: "How are Orders related to Payments?",
    delay: 75,
  },
  {
    role: "ai" as const,
    text: "Orders (AWS) link to Payments (On-Prem) via order_id — a cross-cloud relationship. Each order can have multiple payments. I'm 95% confident this FK exists based on naming patterns and data analysis.",
    delay: 100,
  },
];

export const ChatScene: React.FC = () => {
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
      {/* Background glow */}
      <div
        style={{
          position: "absolute",
          bottom: "10%",
          right: "20%",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${theme.accent}10, transparent 70%)`,
          filter: "blur(100px)",
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
            fontSize: 48,
            fontWeight: 800,
            background: `linear-gradient(135deg, ${theme.indigo[400]}, ${theme.accent})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Ask Your Database Anything
        </div>

        {/* Subtitle */}
        <div
          style={{
            opacity: titleOpacity,
            fontSize: 20,
            color: theme.muted,
            marginTop: -16,
          }}
        >
          New to the team? Get instant answers — no documentation needed
        </div>

        {/* Chat window */}
        <div
          style={{
            width: 900,
            borderRadius: 20,
            border: `1px solid ${theme.border}`,
            background: theme.slate[900],
            overflow: "hidden",
            boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
          }}
        >
          {/* Chat header */}
          <div
            style={{
              padding: "14px 24px",
              borderBottom: `1px solid ${theme.border}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: "#10b981",
                }}
              />
              <span style={{ fontSize: 14, color: theme.muted, fontWeight: 600 }}>
                Schema Advisor — AI Assistant
              </span>
            </div>
            <span style={{ fontSize: 12, color: theme.slate[500] }}>
              4 databases connected
            </span>
          </div>

          {/* Messages */}
          <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 18 }}>
            {chatMessages.map((msg, i) => {
              const msgEntrance = spring({
                frame: frame - msg.delay,
                fps,
                config: { damping: 200 },
              });
              const msgOpacity = interpolate(
                frame,
                [msg.delay, msg.delay + 10],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              );

              let displayText = msg.text;
              if (msg.role === "ai") {
                const charsToShow = Math.floor(
                  interpolate(
                    frame,
                    [msg.delay + 5, msg.delay + 5 + msg.text.length * 0.35],
                    [0, msg.text.length],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
                  )
                );
                displayText = msg.text.slice(0, charsToShow);
              }

              const isUser = msg.role === "user";

              return (
                <div
                  key={i}
                  style={{
                    opacity: msgOpacity,
                    transform: `translateY(${interpolate(msgEntrance, [0, 1], [10, 0])}px)`,
                    display: "flex",
                    justifyContent: isUser ? "flex-end" : "flex-start",
                  }}
                >
                  <div
                    style={{
                      maxWidth: "78%",
                      padding: "12px 18px",
                      borderRadius: isUser ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                      background: isUser
                        ? `linear-gradient(135deg, ${theme.indigo[600]}, ${theme.indigo[500]})`
                        : theme.slate[800],
                      border: isUser ? "none" : `1px solid ${theme.border}`,
                      fontSize: 15,
                      lineHeight: 1.6,
                      color: theme.foreground,
                    }}
                  >
                    {displayText}
                    {msg.role === "ai" && displayText.length < msg.text.length && (
                      <span style={{ opacity: frame % 15 < 8 ? 1 : 0, color: theme.indigo[400] }}>
                        |
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
