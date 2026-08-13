import { useSelector } from "react-redux";
import {
  cpuVendorSelector,
  intelTdpAvailableSelector,
} from "../redux-modules/settingsSlice";
import { CpuVendors } from "../utils/constants";

export const useIsIntel = () => {
  const cpuVendor = useSelector(cpuVendorSelector);

  if (cpuVendor === CpuVendors.INTEL) {
    // intel doesn't support different GPU modes, only gpu freq
    return true;
  }

  return false;
};

// Whether the msi-wmi-platform firmware-attribute interface is present on
// this kernel. RAPL is inert on hardware where it exists at all, so Intel
// TDP control is only functional when this is true. Undefined until
// settings load; irrelevant (never read) on non-Intel devices.
export const useIntelTdpAvailable = () => useSelector(intelTdpAvailableSelector);

export default useIsIntel;
