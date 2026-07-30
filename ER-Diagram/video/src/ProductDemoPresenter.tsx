import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Video } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { LogoIntro } from "./scenes/LogoIntro";
import { ProblemStatement } from "./scenes/ProblemStatement";
import { ConnectScene } from "./scenes/ConnectScene";
import { VisualizeScene } from "./scenes/VisualizeScene";
import { ChatScene } from "./scenes/ChatScene";
import { ExportScene } from "./scenes/ExportScene";
import { SubtitleBar } from "./components/SubtitleBar";
import { KenBurns } from "./components/KenBurns";
import { FPS } from "./theme";

const sec = (s: number) => Math.ceil(s * FPS);
const TRANSITION = 15;

// ============================================================
// HeyGen video is 52.6s total
// Divide proportionally by script section length
// ============================================================
const PRESENTER_TOTAL = 52.6;

// Approximate timestamps in presenter video per section
// Based on script word count proportions
const SCENE_TIMES = {
  scene1: { start: 0, duration: 3.5 },     // "Introducing DataLake..."
  scene2: { start: 3.5, duration: 11 },    // "Understanding a database..."
  scene3: { start: 14.5, duration: 8 },    // "Connect to any cloud..."
  scene4: { start: 22.5, duration: 15 },   // "See your entire schema..."
  scene5: { start: 37.5, duration: 7.5 },  // "Ask your database..."
  scene6: { start: 45, duration: 7.6 },    // "AI auto-documentation..."
};

// Scene durations match presenter video sections + 1s buffer
const LOGO_DURATION = sec(SCENE_TIMES.scene1.duration + 1);
const PROBLEM_DURATION = sec(SCENE_TIMES.scene2.duration + 1);
const CONNECT_DURATION = sec(SCENE_TIMES.scene3.duration + 1);
const VISUALIZE_DURATION = sec(SCENE_TIMES.scene4.duration + 1);
const CHAT_DURATION = sec(SCENE_TIMES.scene5.duration + 1);
const EXPORT_DURATION = sec(SCENE_TIMES.scene6.duration + 1);

// Scene starts
const S1 = 0;
const S2 = LOGO_DURATION - TRANSITION;
const S3 = S2 + PROBLEM_DURATION - TRANSITION;
const S4 = S3 + CONNECT_DURATION - TRANSITION;
const S5 = S4 + VISUALIZE_DURATION - TRANSITION;
const S6 = S5 + CHAT_DURATION - TRANSITION;

export const PRESENTER_TOTAL_DURATION =
  LOGO_DURATION + PROBLEM_DURATION + CONNECT_DURATION +
  VISUALIZE_DURATION + CHAT_DURATION + EXPORT_DURATION -
  5 * TRANSITION;

// Subtitles — short summaries per scene
const subtitles = [
  { text: "Introducing DataLake Orchestrator by ZionAi",
    startFrame: S1 + sec(0.3), endFrame: S1 + sec(SCENE_TIMES.scene1.duration) },
  { text: "What if weeks became seconds?",
    startFrame: S2 + sec(0.3), endFrame: S2 + sec(SCENE_TIMES.scene2.duration) },
  { text: "Connect to any cloud — Azure, Google Cloud, AWS, or on-premises",
    startFrame: S3 + sec(0.3), endFrame: S3 + sec(SCENE_TIMES.scene3.duration) },
  { text: "Instantly see your entire schema with cross-cloud relationships",
    startFrame: S4 + sec(0.3), endFrame: S4 + sec(SCENE_TIMES.scene4.duration) },
  { text: "Ask your database anything in plain English",
    startFrame: S5 + sec(0.3), endFrame: S5 + sec(SCENE_TIMES.scene5.duration) },
  { text: "Enterprise features at a fraction of the cost",
    startFrame: S6 + sec(0.3), endFrame: S6 + sec(SCENE_TIMES.scene6.duration) },
];

export const ProductDemoPresenter: React.FC = () => {
  return (
    <AbsoluteFill>
      {/* Video scenes with Ken Burns */}
      <AbsoluteFill>
        <TransitionSeries>
          <TransitionSeries.Sequence durationInFrames={LOGO_DURATION}>
            <LogoIntro />
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={PROBLEM_DURATION}>
            <ProblemStatement />
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={CONNECT_DURATION}>
            <ConnectScene />
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={slide({ direction: "from-right" })}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={VISUALIZE_DURATION}>
            <VisualizeScene />
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={slide({ direction: "from-right" })}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={CHAT_DURATION}>
            <ChatScene />
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={EXPORT_DURATION}>
            <ExportScene />
          </TransitionSeries.Sequence>
        </TransitionSeries>
      </AbsoluteFill>

      {/* HeyGen presenter video — bottom right corner */}
      {/* Full video plays from start, audio is the narration */}
      <Sequence from={0} layout="none">
        <div
          style={{
            position: "absolute",
            bottom: 20,
            right: 20,
            width: 220,
            height: 390,
            borderRadius: 20,
            overflow: "hidden",
            border: "2px solid rgba(255,255,255,0.15)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
            zIndex: 100,
          }}
        >
          <Video
            src={staticFile("presenter-cropped.mp4")}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        </div>
      </Sequence>

      {/* Subtitles */}
      <SubtitleBar subtitles={subtitles} />
    </AbsoluteFill>
  );
};
