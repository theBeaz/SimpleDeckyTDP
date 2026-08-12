import { FC } from "react";
import { usePl2Mode } from "../../hooks/usePl2";
import { Pl2Modes } from "../../backend/utils";
import { DeckySlider, NotchLabel } from "./DeckyFrontendLib";
import t from "../../i18n/i18n";

// Pl2Modes values ("flat"/"offset"/"max") don't support TS's enum-reverse-mapping
// trick that GpuModeSlider relies on (key text != value text), so map explicitly.
const PL2_MODE_ORDER: Pl2Modes[] = [
  Pl2Modes.FLAT,
  Pl2Modes.OFFSET,
  Pl2Modes.MAX,
];

const Pl2ModeSlider: FC<{ showSeparator: boolean }> = ({ showSeparator }) => {
  const { pl2Mode, setPl2Mode } = usePl2Mode();

  const handleSliderChange = (value: number) => {
    return setPl2Mode(PL2_MODE_ORDER[value]);
  };

  const PL2_MODE_LABELS: { [key in Pl2Modes]: string } = {
    [Pl2Modes.FLAT]: t("PL2_MODE_FLAT", "Flat"),
    [Pl2Modes.OFFSET]: t("PL2_MODE_OFFSET", "Offset"),
    [Pl2Modes.MAX]: t("PL2_MODE_MAX", "Max"),
  };

  const MODES: NotchLabel[] = PL2_MODE_ORDER.map((mode, idx) => ({
    notchIndex: idx,
    label: PL2_MODE_LABELS[mode],
    value: idx,
  }));

  const sliderValue = PL2_MODE_ORDER.indexOf(pl2Mode);

  return (
    <DeckySlider
      label={t("PL2_MODE_LABEL", "PL2 Mode")}
      value={sliderValue}
      min={0}
      max={MODES.length - 1}
      step={1}
      notchCount={MODES.length}
      notchLabels={MODES}
      notchTicksVisible={true}
      showValue={false}
      bottomSeparator={showSeparator ? "standard" : "none"}
      onChange={handleSliderChange}
    />
  );
};

export default Pl2ModeSlider;
