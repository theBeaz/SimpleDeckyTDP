import os
import decky_plugin
from plugin_settings import get_saved_settings

# The only functional TDP write path on this hardware. RAPL powercap sysfs
# (intel-rapl / intel-rapl-mmio) is inert here: writes succeed and read back
# correctly, but the embedded controller silently overrides them with its own
# stored value. Confirmed by measured package draw (RAPL energy counter) and
# GPU act_freq staying capped even after RAPL writes claimed success -- only
# writes to these firmware attributes actually change measured behaviour.
#
# This comes from Antheas Kapenekakis's msi-wmi-platform patch series and
# uses a per-model quirk system with no discovery API, so other handheld
# models may expose different attribute names or none at all. Gate on the
# interface existing (is_available()), never on a device allowlist.
FW_ATTR_DIR = "/sys/class/firmware-attributes/msi-wmi-platform/attributes"
PL1_DIR = f"{FW_ATTR_DIR}/ppt_pl1_spl"
PL2_DIR = f"{FW_ATTR_DIR}/ppt_pl2_sppt"

PL2_OFFSET_MAX_WATTS = 7
PL2_MODES = ('flat', 'offset', 'max')
DEFAULT_PL2_MODE = 'flat'
DEFAULT_PL2_OFFSET = 7

PL2_MODE_SETTING = 'pl2Mode'
PL2_OFFSET_SETTING = 'pl2Offset'


def is_available():
  # Checked live on every call (no caching): kernel/SteamOS-version
  # dependent, not device-model dependent -- confirmed absent on SteamOS
  # 3.8.16 (kernel 6.16.12-valve24.5-neptune) and present on 3.8.25
  # (6.18.42-valve2-neptune) on the same physical hardware.
  return os.path.isdir(PL1_DIR) and os.path.isdir(PL2_DIR)


def _pl1_current_path():
  return f"{PL1_DIR}/current_value"


def _pl2_current_path():
  return f"{PL2_DIR}/current_value"


def _pl1_min_path():
  return f"{PL1_DIR}/min_value"


def _pl1_max_path():
  return f"{PL1_DIR}/max_value"


def _pl2_min_path():
  return f"{PL2_DIR}/min_value"


def _pl2_max_path():
  return f"{PL2_DIR}/max_value"


def _read_int(path):
  if not path or not os.path.exists(path):
    return None
  try:
    with open(path, 'r') as file:
      return int(file.read().strip())
  except Exception as e:
    decky_plugin.logger.error(f'{__name__} error reading {path}: {e}')
    return None


def _write_verify(path, value_w):
  """Write + mandatory read-back verification.

  On this hardware the failure mode is silent: a write can succeed and even
  read back correctly from the same attribute while the EC quietly ignores
  it in practice, so read-back here is a sanity check, not a guarantee --
  but skipping it entirely is how this bug went unnoticed in the first
  place. Returns the actual value now on disk (which may differ from
  value_w if the write didn't take), or None on a hard I/O error.
  """
  try:
    with open(path, 'w') as file:
      file.write(str(int(value_w)))
  except Exception as e:
    decky_plugin.logger.error(f'{__name__} error writing {value_w} to {path}: {e}')
    return None

  got = _read_int(path)
  if got != value_w:
    decky_plugin.logger.error(
      f'{__name__} write to {path} did not take: wanted {value_w}, got {got}'
    )
  return got


def get_pl1_range():
  return _read_int(_pl1_min_path()), _read_int(_pl1_max_path())


def get_pl2_range():
  return _read_int(_pl2_min_path()), _read_int(_pl2_max_path())


def get_pl1_current():
  return _read_int(_pl1_current_path())


def get_pl2_current():
  return _read_int(_pl2_current_path())


def is_pl2_supported():
  """Whether hardware genuinely exposes independent PL2 headroom.

  Unlike RAPL, ppt_pl1_spl/ppt_pl2_sppt's min_value/max_value are real
  firmware-declared constants (verified on-device), so a real-headroom
  check (pl2_max > pl1_max) is meaningful and safe to require here.
  """
  if not is_available():
    return False
  _, pl1_max = get_pl1_range()
  _, pl2_max = get_pl2_range()
  return pl1_max is not None and pl2_max is not None and pl2_max > pl1_max


def resolve_pl2(pl1, mode, offset, pl2_min, pl2_max):
  """Pure, unit-testable resolution of PL2 given PL1 and the global pl2Mode/pl2Offset.

  PL2 must never end up below PL1 -- the kernel/EC accepts it silently (an
  offset writer and something else fighting has produced PL1 30 / PL2 15 in
  the wild), so this function is the enforcement point, not the hardware.
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

  # floor against max(pl1, pl2_min), not just pl2_min: if pl2_max ever ends
  # up below pl1 (a degenerate state that shouldn't occur on real hardware,
  # but the invariant must hold unconditionally per spec), flooring on
  # pl2_min alone can still return a value below pl1.
  floor = max(pl1, pl2_min)
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


def _write_if_changed(path, target_w, current_w):
  if target_w is None:
    return True
  if current_w is not None and current_w == target_w:
    # avoid poking the EC every poll cycle when nothing changed
    return True

  got = _write_verify(path, target_w)
  return got == target_w


def apply_pl1_pl2(pl1_target):
  """The only Intel TDP write path. Returns False (no writes attempted) when
  the firmware-attribute interface isn't present -- callers must not fall
  back to RAPL, which is inert on hardware where this interface exists."""
  if not is_available():
    decky_plugin.logger.info(
      f'{__name__} msi-wmi-platform firmware attributes not present -- '
      'Intel TDP control unavailable on this kernel'
    )
    return False

  pl1_min, pl1_max = get_pl1_range()
  if pl1_min is not None:
    pl1_target = max(pl1_min, pl1_target)
  if pl1_max is not None:
    pl1_target = min(pl1_max, pl1_target)

  pl2_min, pl2_max = get_pl2_range()
  current_pl1 = get_pl1_current()
  current_pl2 = get_pl2_current()

  mode, offset = get_pl2_settings()

  if pl2_min is None or pl2_max is None:
    # can't safely resolve an independent PL2 without a real declared range
    resolved_pl2 = pl1_target
  else:
    resolved_pl2 = resolve_pl2(pl1_target, mode, offset, pl2_min, pl2_max)

  pl1_path = _pl1_current_path()
  pl2_path = _pl2_current_path()

  # Write order: pick whichever order keeps every intermediate state at
  # PL2 >= PL1. Writing PL1 first is only safe when the new PL1 doesn't
  # exceed the still-old PL2 (NOT "gate on whether the new PL2 exceeds the
  # old PL1" -- that comparison can still produce a PL2<PL1 intermediate,
  # e.g. raising flat 10/10 -> 20/20 would briefly hit 20/10).
  write_pl1_first = current_pl2 is None or pl1_target <= current_pl2

  ok = True
  if write_pl1_first:
    ok = _write_if_changed(pl1_path, pl1_target, current_pl1) and ok
    ok = _write_if_changed(pl2_path, resolved_pl2, current_pl2) and ok
  else:
    ok = _write_if_changed(pl2_path, resolved_pl2, current_pl2) and ok
    ok = _write_if_changed(pl1_path, pl1_target, current_pl1) and ok

  return ok
