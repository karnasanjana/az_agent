import { AbsoluteFill } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { LogoIntro } from "./scenes/LogoIntro";
import { ProblemStatement } from "./scenes/ProblemStatement";
import { ConnectScene } from "./scenes/ConnectScene";
import { VisualizeScene } from "./scenes/VisualizeScene";
import { ChatScene } from "./scenes/ChatScene";
import { ExportScene } from "./scenes/ExportScene";
import { FPS } from "./theme";

// Scene durations in frames (at 30fps)
const LOGO_DURATION = 4 * FPS;        // 4s
const PROBLEM_DURATION = 7 * FPS;     // 7s — 6 pain steps + solution reveal
const CONNECT_DURATION = 7 * FPS;     // 7s — 4 clouds clicking sequentially
const VISUALIZE_DURATION = 16 * FPS;  // 16s — 4 waves of tables + cross-cloud
const CHAT_DURATION = 6 * FPS;        // 6s
const EXPORT_DURATION = 4 * FPS;      // 4s

const TRANSITION_DURATION = 15; // 0.5s transition

export const ProductDemo: React.FC = () => {
  return (
    <AbsoluteFill>
      <TransitionSeries>
        {/* 1. Logo Intro */}
        <TransitionSeries.Sequence durationInFrames={LOGO_DURATION}>
          <LogoIntro />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANSITION_DURATION })}
        />

        {/* 2. Problem Statement */}
        <TransitionSeries.Sequence durationInFrames={PROBLEM_DURATION}>
          <ProblemStatement />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANSITION_DURATION })}
        />

        {/* 3. Connect to Data Sources */}
        <TransitionSeries.Sequence durationInFrames={CONNECT_DURATION}>
          <ConnectScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: TRANSITION_DURATION })}
        />

        {/* 4. Visualize ER Diagrams */}
        <TransitionSeries.Sequence durationInFrames={VISUALIZE_DURATION}>
          <VisualizeScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: TRANSITION_DURATION })}
        />

        {/* 5. Talk to Your Data (AI Chat) */}
        <TransitionSeries.Sequence durationInFrames={CHAT_DURATION}>
          <ChatScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANSITION_DURATION })}
        />

        {/* 6. Built for Teams */}
        <TransitionSeries.Sequence durationInFrames={EXPORT_DURATION}>
          <ExportScene />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
