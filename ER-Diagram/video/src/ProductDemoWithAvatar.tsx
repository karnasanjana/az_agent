import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Audio } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { LogoIntro } from "./scenes/LogoIntro";
import { ProblemStatement } from "./scenes/ProblemStatement";
import { ConnectScene } from "./scenes/ConnectScene";
import { VisualizeScene } from "./scenes/VisualizeScene";
import { ChatScene } from "./scenes/ChatScene";
import { ExportScene } from "./scenes/ExportScene";
import { Avatar } from "./components/Avatar";
import { SubtitleBar } from "./components/SubtitleBar";
import { KenBurns } from "./components/KenBurns";
import { FPS } from "./theme";

const sec = (s: number) => Math.ceil(s * FPS);
const TRANSITION = 15; // 0.5s

// ============================================================
// Audio durations (measured from generated files)
// ============================================================
const AUDIO = {
  scene1: 2.69,   // "Introducing DataLake Orchestrator..."
  scene2: 10.74,  // Problem — business impact before/after
  scene3: 8.01,   // Connect to clouds
  scene4: 14.36,  // Visualize schema
  scene5: 7.00,   // Chat with AI
  scene6: 5.69,   // Features
};

// ============================================================
// Scene durations = delay + audio + 0.5s buffer
// Scene ends exactly when audio finishes (+ tiny buffer)
// No wasted time, no overlap possible
// ============================================================
const DELAY_S1 = 0;    // no delay for logo
const DELAY_S2 = 0;    // no delay for problem
const DELAY_S3 = 0;    // no delay for connect
const DELAY = 2;        // 2s before scenes 4-6

const LOGO_DURATION = sec(DELAY_S1 + AUDIO.scene1 + 3);
const PROBLEM_DURATION = sec(DELAY_S2 + AUDIO.scene2 + 9);
const CONNECT_DURATION = sec(DELAY_S3 + AUDIO.scene3 + 4.5);
const VISUALIZE_DURATION = sec(DELAY + AUDIO.scene4 + 8.5);
const CHAT_DURATION = sec(DELAY + AUDIO.scene5 + 2.5);
const EXPORT_DURATION = sec(DELAY + AUDIO.scene6 + 4.5);

// Scene absolute start frames
const S1 = 0;
const S2 = LOGO_DURATION - TRANSITION;
const S3 = S2 + PROBLEM_DURATION - TRANSITION;
const S4 = S3 + CONNECT_DURATION - TRANSITION;
const S5 = S4 + VISUALIZE_DURATION - TRANSITION;
const S6 = S5 + CHAT_DURATION - TRANSITION;

// Total composition
export const AVATAR_TOTAL_DURATION =
  LOGO_DURATION + PROBLEM_DURATION + CONNECT_DURATION +
  VISUALIZE_DURATION + CHAT_DURATION + EXPORT_DURATION -
  5 * TRANSITION;

// ============================================================
// Audio starts — delay into each scene, finishes before scene ends
// ============================================================
const voiceoverAudio = [
  { file: "voiceover/scene1.mp3", startFrame: S1 + sec(DELAY_S1) },
  { file: "voiceover/scene2.mp3", startFrame: S2 + sec(DELAY_S2) },
  { file: "voiceover/scene3.mp3", startFrame: S3 + sec(DELAY_S3) },
  { file: "voiceover/scene4.mp3", startFrame: S4 + sec(DELAY) },
  { file: "voiceover/scene5.mp3", startFrame: S5 + sec(DELAY) },
  { file: "voiceover/scene6.mp3", startFrame: S6 + sec(DELAY) },
];

// ============================================================
// Subtitles — synced to audio
// ============================================================
const subtitles = [
  { text: "Introducing DataLake Orchestrator by ZionAi",
    startFrame: S1 + sec(DELAY_S1), endFrame: S1 + sec(DELAY_S1 + AUDIO.scene1) },
  { text: "What if weeks became seconds?",
    startFrame: S2 + sec(DELAY_S2), endFrame: S2 + sec(DELAY_S2 + AUDIO.scene2) },
  { text: "Connect to any cloud — Azure, Google Cloud, AWS, or on-premises",
    startFrame: S3 + sec(DELAY_S3), endFrame: S3 + sec(DELAY_S3 + AUDIO.scene3) },
  { text: "Instantly see your entire schema with cross-cloud relationships",
    startFrame: S4 + sec(DELAY), endFrame: S4 + sec(DELAY + AUDIO.scene4) },
  { text: "Ask your database anything in plain English",
    startFrame: S5 + sec(DELAY), endFrame: S5 + sec(DELAY + AUDIO.scene5) },
  { text: "Enterprise features at a fraction of the cost",
    startFrame: S6 + sec(DELAY), endFrame: S6 + sec(DELAY + AUDIO.scene6) },
];

// ============================================================
// Component
// ============================================================
export const ProductDemoWithAvatar: React.FC = () => {
  return (
    <AbsoluteFill>
      {/* Video scenes */}
      <AbsoluteFill>
        <TransitionSeries>
          <TransitionSeries.Sequence durationInFrames={LOGO_DURATION}>
            <KenBurns direction="in" intensity={0.04}>
              <LogoIntro />
            </KenBurns>
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={PROBLEM_DURATION}>
            <KenBurns direction="out" intensity={0.05}>
              <ProblemStatement />
            </KenBurns>
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={CONNECT_DURATION}>
            <KenBurns direction="in" intensity={0.05}>
              <ConnectScene />
            </KenBurns>
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={slide({ direction: "from-right" })}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={VISUALIZE_DURATION}>
            <KenBurns direction="in" intensity={0.06}>
              <VisualizeScene />
            </KenBurns>
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={slide({ direction: "from-right" })}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={CHAT_DURATION}>
            <KenBurns direction="out" intensity={0.04}>
              <ChatScene />
            </KenBurns>
          </TransitionSeries.Sequence>
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />
          <TransitionSeries.Sequence durationInFrames={EXPORT_DURATION}>
            <KenBurns direction="in" intensity={0.05}>
              <ExportScene />
            </KenBurns>
          </TransitionSeries.Sequence>
        </TransitionSeries>
      </AbsoluteFill>

      {/* Voiceover — one audio file per scene */}
      {voiceoverAudio.map((vo, i) => (
        <Sequence key={i} from={vo.startFrame} layout="none">
          <Audio src={staticFile(vo.file)} volume={0.9} />
        </Sequence>
      ))}

      {/* Avatar — bottom-right, appears after logo */}
      <Sequence from={S2} layout="none">
        <div
          style={{
            position: "absolute",
            bottom: 20,
            right: 30,
            zIndex: 100,
            filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.5))",
          }}
        >
          <Avatar isSpeaking={true} />
        </div>
      </Sequence>

      {/* Subtitles */}
      <SubtitleBar subtitles={subtitles} />
    </AbsoluteFill>
  );
};
