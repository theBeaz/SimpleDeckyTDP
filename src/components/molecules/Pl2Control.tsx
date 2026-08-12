import useIsIntel from "../../hooks/useIsIntel";
import { usePl2Mode, usePl2Supported } from "../../hooks/usePl2";
import { Pl2Modes } from "../../backend/utils";
import Pl2ModeSlider from "../atoms/Pl2ModeSlider";
import Pl2OffsetSlider from "../atoms/Pl2OffsetSlider";
import ErrorBoundary from "../ErrorBoundary";
import { DeckyRow } from "../atoms/DeckyFrontendLib";

const Pl2Control = () => {
  const isIntel = useIsIntel();
  const pl2Supported = usePl2Supported();
  const { pl2Mode } = usePl2Mode();

  if (!isIntel || !pl2Supported) {
    // PL2 (RAPL short-term boost) is an Intel concept, and only worth showing
    // when the hardware actually exposes headroom beyond PL1's max
    return null;
  }

  return (
    <ErrorBoundary title="PL2 Control">
      <DeckyRow>
        <Pl2ModeSlider showSeparator={pl2Mode === Pl2Modes.OFFSET} />
      </DeckyRow>
      <DeckyRow>
        <Pl2OffsetSlider />
      </DeckyRow>
    </ErrorBoundary>
  );
};

export default Pl2Control;
