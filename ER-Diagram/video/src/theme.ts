// ZionAi Brand Theme — matches frontend/src/app/globals.css
export const theme = {
  bg: "#0B0E14",
  foreground: "#f8fafc",
  primary: "#6366f1",
  primaryLight: "#818cf8",
  accent: "#a855f7",
  surface: "rgba(255, 255, 255, 0.03)",
  border: "rgba(255, 255, 255, 0.08)",
  muted: "#94a3b8",
  slate: {
    50: "#f8fafc",
    100: "#f1f5f9",
    200: "#e2e8f0",
    300: "#cbd5e1",
    400: "#9ba3af",
    500: "#6b7280",
    600: "#4b5563",
    700: "#303236",
    800: "#212225",
    900: "#18191b",
    950: "#111214",
  },
  indigo: {
    400: "#818cf8",
    500: "#6366f1",
    600: "#4f46e5",
    900: "#312e81",
  },
  logoGradient: {
    start: "#002AEB",
    mid: "#114FEE",
    end: "#95FFA7",
  },
} as const;

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
