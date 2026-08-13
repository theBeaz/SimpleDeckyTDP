import { useTdpRange } from "../../hooks/useTdpRange";
import { useSetTdp } from "../../hooks/useTdpProfiles";
import { useSelector } from "react-redux";
import { getCurrentTdpInfoSelector } from "../../redux-modules/settingsSlice";
import useIsIntel, { useIntelTdpAvailable } from "../../hooks/useIsIntel";
import ErrorBoundary from "../ErrorBoundary";
import { DeckyField, DeckyRow, DeckySlider } from "../atoms/DeckyFrontendLib";
import t from '../../i18n/i18n';

export const TdpSlider = ({ disabled = false }: { disabled?: boolean }) => {
  const [minTdp, maxTdp] = useTdpRange();
  const setTdp = useSetTdp();
  const { tdp } = useSelector(getCurrentTdpInfoSelector);
  const isIntel = useIsIntel();
  const intelTdpAvailable = useIntelTdpAvailable();

  if (isIntel && intelTdpAvailable === false) {
    // RAPL is inert on Intel hardware where the msi-wmi-platform
    // firmware-attribute interface exists at all -- writes succeed and read
    // back correctly while the EC silently ignores them, so a working-
    // looking slider here would be actively misleading rather than merely
    // non-functional. Disable and explain instead of writing RAPL as a
    // "best effort".
    return (
      <DeckyRow>
        <ErrorBoundary title="TDP Slider">
          <DeckyField disabled label={t('TDP_SLIDER_LABEL', 'TDP (Watts)')}>
            {t(
              'TDP_UNAVAILABLE_NO_FW_ATTR',
              'TDP control requires a kernel with the msi-wmi-platform firmware-attribute interface. It is not present on this kernel.'
            )}
          </DeckyField>
        </ErrorBoundary>
      </DeckyRow>
    );
  }

  return (
    <DeckyRow>
      <ErrorBoundary title="TDP Slider">
        <DeckySlider
          value={tdp}
          label={t('TDP_SLIDER_LABEL', 'TDP (Watts)')}
          min={minTdp}
          max={maxTdp}
          step={1}
          disabled={disabled}
          onChange={(newTdp) => setTdp(newTdp)}
          notchTicksVisible
          showValue
        />
      </ErrorBoundary>
    </DeckyRow>
  );
};
