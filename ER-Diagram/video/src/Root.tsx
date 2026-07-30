import { Composition, Folder } from "remotion";
import { ProductDemo } from "./ProductDemo";
import { ProductDemoWithAvatar, AVATAR_TOTAL_DURATION } from "./ProductDemoWithAvatar";
import { ProductDemoPresenter, PRESENTER_TOTAL_DURATION } from "./ProductDemoPresenter";
import { FPS, WIDTH, HEIGHT } from "./theme";

// Original (no audio): 44s - 5 transitions
const TOTAL_DURATION = 44 * FPS - 5 * 15;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Folder name="Demos">
        <Composition
          id="ProductDemo"
          component={ProductDemo}
          durationInFrames={TOTAL_DURATION}
          fps={FPS}
          width={WIDTH}
          height={HEIGHT}
        />
        <Composition
          id="ProductDemoWithAvatar"
          component={ProductDemoWithAvatar}
          durationInFrames={AVATAR_TOTAL_DURATION}
          fps={FPS}
          width={WIDTH}
          height={HEIGHT}
        />
        <Composition
          id="ProductDemoPresenter"
          component={ProductDemoPresenter}
          durationInFrames={PRESENTER_TOTAL_DURATION}
          fps={FPS}
          width={WIDTH}
          height={HEIGHT}
        />
      </Folder>
    </>
  );
};
