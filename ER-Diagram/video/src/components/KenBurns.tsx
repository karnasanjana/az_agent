import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from "remotion";

type FocalZoomProps = {
  // Where to zoom toward: percentage of screen (50,50 = center)
  focalX?: number; // 0-100, default 50
  focalY?: number; // 0-100, default 50
  // Zoom range
  scaleFrom?: number; // default 1.0
  scaleTo?: number;   // default 1.3
  // Optional: multi-stage zoom (zoom in then out)
  stages?: {
    at: number;    // 0-1 progress
    scale: number;
    focalX?: number;
    focalY?: number;
  }[];
  children: React.ReactNode;
};

export const KenBurns: React.FC<FocalZoomProps> = ({
  focalX = 50,
  focalY = 50,
  scaleFrom = 1.0,
  scaleTo = 1.25,
  stages,
  children,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const progress = interpolate(
    frame,
    [0, durationInFrames],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad) }
  );

  let scale: number;
  let originX: number;
  let originY: number;

  if (stages && stages.length > 0) {
    // Multi-stage zoom: interpolate between keyframes
    const allPoints = [
      { at: 0, scale: scaleFrom, focalX, focalY },
      ...stages.map((s) => ({ at: s.at, scale: s.scale, focalX: s.focalX ?? focalX, focalY: s.focalY ?? focalY })),
    ];
    // Sort by progress
    allPoints.sort((a, b) => a.at - b.at);

    // Find current segment
    let segIdx = 0;
    for (let i = 0; i < allPoints.length - 1; i++) {
      if (progress >= allPoints[i].at) segIdx = i;
    }
    const from = allPoints[segIdx];
    const to = allPoints[Math.min(segIdx + 1, allPoints.length - 1)];

    const segProgress = from.at === to.at ? 1 : interpolate(
      progress,
      [from.at, to.at],
      [0, 1],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const eased = Easing.inOut(Easing.quad)(segProgress);
    scale = interpolate(eased, [0, 1], [from.scale, to.scale]);
    originX = interpolate(eased, [0, 1], [from.focalX, to.focalX]);
    originY = interpolate(eased, [0, 1], [from.focalY, to.focalY]);
  } else {
    // Simple two-point zoom
    scale = interpolate(progress, [0, 1], [scaleFrom, scaleTo]);
    originX = focalX;
    originY = focalY;
  }

  return (
    <AbsoluteFill
      style={{
        transform: `scale(${scale})`,
        transformOrigin: `${originX}% ${originY}%`,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
