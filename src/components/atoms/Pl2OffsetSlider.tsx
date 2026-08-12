import { FC } from "react";
import { usePl2Mode, usePl2Offset } from "../../hooks/usePl2";
import { Pl2Modes } from "../../backend/utils";
import { PL2_OFFSET_MAX_WATTS } from "../../utils/constants";
import { DeckySlider } from "./DeckyFrontendLib";
import t from "../../i18n/i18n";

const Pl2OffsetSlider: FC = () => {
  const { pl2Mode } = usePl2Mode();
  const { pl2Offset, setPl2Offset } = usePl2Offset();

  if (pl2Mode !== Pl2Modes.OFFSET) {
    // only meaningful in Offset mode
    return null;
  }

  return (
    <DeckySlider
      label={t("PL2_OFFSET_LABEL", "PL2 Offset")}
      value={pl2Offset}
      description={`+${pl2Offset}W`}
      min={0}
      max={PL2_OFFSET_MAX_WATTS}
      step={1}
      showValue
      bottomSeparator="none"
      onChange={setPl2Offset}
    />
  );
};

export default Pl2OffsetSlider;
