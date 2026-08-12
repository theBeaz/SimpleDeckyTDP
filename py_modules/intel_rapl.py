import os
import decky_plugin
from plugin_settings import get_saved_settings

MSI_WMI_ATTR_DIR = "/sys/class/firmware-attributes/msi-wmi-platform/attributes"
MSI_WMI_PL1_DIR = f"{MSI_WMI_ATTR_DIR}/ppt_pl1_spl"
MSI_WMI_PL2_DIR = f"{MSI_WMI_ATTR_DIR}/ppt_pl2_sppt"

# same underlying sysfs nodes as cpu_utils.INTEL_TDP_PREFIX / INTEL_LEGACY_TDP_PREFIX
RAPL_MMIO_PREFIX = "/sys/devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0"
RAPL_LEGACY_PREFIX = "/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0"

MICROWATTS_PER_WATT = 1_000_000

PL2_OFFSET_MAX_WATTS = 7
PL2_MODES = ('flat', 'offset', 'max')
DEFAULT_PL2_MODE = 'flat'
DEFAULT_PL2_OFFSET = 7

PL2_MODE_SETTING = 'pl2Mode'
PL2_OFFSET_SETTING = 'pl2Offset'

MSI_WMI = 'msi_wmi'
RAPL_MMIO = 'rapl_mmio'
RAPL_LEGACY = 'rapl_legacy'


def detect_interface():
  # Checked live on every call (no caching): the firmware-attributes directory is
  # kernel/SteamOS-version dependent, not device-model dependent, and can appear or
  # disappear across an OS update on the same physical device.
  if os.path.isdir(MSI_WMI_PL1_DIR) and os.path.isdir(MSI_WMI_PL2_DIR):
    return MSI_WMI
  if os.path.isdir(RAPL_MMIO_PREFIX):
    return RAPL_MMIO
  if os.path.isdir(RAPL_LEGACY_PREFIX):
    return RAPL_LEGACY
  return None


def _pl1_current_path(interface):
  if interface == MSI_WMI:
    return f"{MSI_WMI_PL1_DIR}/current_value"
  prefix = RAPL_MMIO_PREFIX if interface == RAPL_MMIO else RAPL_LEGACY_PREFIX
  return f"{prefix}/constraint_0_power_limit_uw"


def _pl2_current_path(interface):
  if interface == MSI_WMI:
    return f"{MSI_WMI_PL2_DIR}/current_value"
  prefix = RAPL_MMIO_PREFIX if interface == RAPL_MMIO else RAPL_LEGACY_PREFIX
  return f"{prefix}/constraint_1_power_limit_uw"


def _pl1_min_path(interface):
  if interface == MSI_WMI:
    return f"{MSI_WMI_PL1_DIR}/min_value"
  # RAPL powercap exposes no constraint_*_min_power_uw
  return None


def _pl1_max_path(interface):
  if interface == MSI_WMI:
    return f"{MSI_WMI_PL1_DIR}/max_value"
  prefix = RAPL_MMIO_PREFIX if interface == RAPL_MMIO else RAPL_LEGACY_PREFIX
  return f"{prefix}/constraint_0_max_power_uw"


def _pl2_min_path(interface):
  if interface == MSI_WMI:
    return f"{MSI_WMI_PL2_DIR}/min_value"
  return None


def _pl2_max_path(interface):
  if interface == MSI_WMI:
    return f"{MSI_WMI_PL2_DIR}/max_value"
  prefix = RAPL_MMIO_PREFIX if interface == RAPL_MMIO else RAPL_LEGACY_PREFIX
  return f"{prefix}/constraint_1_max_power_uw"


def _read_int(path):
  if not path or not os.path.exists(path):
    return None
  try:
    with open(path, 'r') as file:
      return int(file.read().strip())
  except Exception as e:
    decky_plugin.logger.error(f'{__name__} error reading {path}: {e}')
    return None


def _write_int(path, value):
  try:
    with open(path, 'w') as file:
      file.write(str(int(value)))
    return True
  except Exception as e:
    decky_plugin.logger.error(f'{__name__} error writing {value} to {path}: {e}')
    return False


def _to_watts(raw, interface):
  if raw is None:
    return None
  if interface == MSI_WMI:
    return raw
  return raw // MICROWATTS_PER_WATT


def _to_native(watts, interface):
  if interface == MSI_WMI:
    return watts
  return watts * MICROWATTS_PER_WATT


def get_pl1_range(interface):
  min_w = _to_watts(_read_int(_pl1_min_path(interface)), interface)
  max_w = _to_watts(_read_int(_pl1_max_path(interface)), interface)
  return min_w, max_w


def get_pl2_max(interface):
  return _to_watts(_read_int(_pl2_max_path(interface)), interface)


def get_pl2_min(interface):
  return _to_watts(_read_int(_pl2_min_path(interface)), interface)


def get_pl1_current(interface):
  return _to_watts(_read_int(_pl1_current_path(interface)), interface)


def get_pl2_current(interface):
  return _to_watts(_read_int(_pl2_current_path(interface)), interface)


def resolve_pl2(pl1, mode, offset, pl2_max, pl2_min=None):
  """Pure, unit-testable resolution of PL2 given PL1 and the global pl2Mode/pl2Offset.

  PL2 must never end up below PL1 -- the kernel accepts and silently keeps a
  PL2 < PL1 state, so this function (not the hardware) is the enforcement point.
  """
  # defensive cap: protects against a hand-edited settings.json with offset > 7
  safe_offset = max(0, min(PL2_OFFSET_MAX_WATTS, offset))

  if mode == 'max':
    target = pl2_max
  elif mode == 'offset':
    target = pl1 + safe_offset
  else:
    # 'flat' or any unrecognized mode falls back to the safe/current behaviour
    target = pl1

  floor = max(pl1, pl2_min) if pl2_min is not None else pl1
  return max(floor, min(pl2_max, target))


def get_pl2_settings():
  settings = get_saved_settings()

  mode = settings.get(PL2_MODE_SETTING, DEFAULT_PL2_MODE)
  if mode not in PL2_MODES:
    mode = DEFAULT_PL2_MODE

  offset = settings.get(PL2_OFFSET_SETTING, DEFAULT_PL2_OFFSET)
  if not isinstance(offset, int) or isinstance(offset, bool):
    offset = DEFAULT_PL2_OFFSET
  offset = max(0, min(PL2_OFFSET_MAX_WATTS, offset))

  return mode, offset


def _write_watts_if_changed(path, target_watts, current_watts, interface):
  if target_watts is None:
    return True
  if current_watts is not None and current_watts == target_watts:
    # avoid poking the EC every poll cycle when nothing changed
    return True

  native_value = _to_native(target_watts, interface)
  ok = _write_int(path, native_value)
  if not ok:
    return False

  readback = _to_watts(_read_int(path), interface)
  if readback == target_watts:
    return True

  # retry once on mismatch
  ok = _write_int(path, native_value)
  if not ok:
    return False
  readback = _to_watts(_read_int(path), interface)
  return readback == target_watts


def apply_pl1_pl2(pl1_target):
  interface = detect_interface()
  if interface is None:
    decky_plugin.logger.info(f'{__name__} no known Intel RAPL/firmware-attribute interface found')
    return False

  pl1_min, pl1_max = get_pl1_range(interface)
  if pl1_min is not None:
    pl1_target = max(pl1_min, pl1_target)
  if pl1_max is not None:
    pl1_target = min(pl1_max, pl1_target)

  pl2_max = get_pl2_max(interface)
  pl2_min = get_pl2_min(interface)
  current_pl1 = get_pl1_current(interface)
  current_pl2 = get_pl2_current(interface)

  mode, offset = get_pl2_settings()

  if pl2_max is None:
    # no discoverable PL2 ceiling on this interface -- degrade to today's flat
    # behaviour rather than guessing at a safe ceiling
    resolved_pl2 = pl1_target
  else:
    resolved_pl2 = resolve_pl2(pl1_target, mode, offset, pl2_max, pl2_min)

  pl1_path = _pl1_current_path(interface)
  pl2_path = _pl2_current_path(interface)

  # Write order: pick whichever order keeps every intermediate state at PL2 >= PL1.
  # Writing PL1 first is only safe when the new PL1 doesn't exceed the still-old PL2.
  write_pl1_first = current_pl2 is None or pl1_target <= current_pl2

  ok = True
  if write_pl1_first:
    ok = _write_watts_if_changed(pl1_path, pl1_target, current_pl1, interface) and ok
    ok = _write_watts_if_changed(pl2_path, resolved_pl2, current_pl2, interface) and ok
  else:
    ok = _write_watts_if_changed(pl2_path, resolved_pl2, current_pl2, interface) and ok
    ok = _write_watts_if_changed(pl1_path, pl1_target, current_pl1, interface) and ok

  return ok
