import sys
import types

# decky_plugin / plugin_settings are only importable inside the real Decky Loader
# runtime; stub them out so resolve_pl2 (pure, no I/O) can be tested standalone.
if 'decky_plugin' not in sys.modules:
  fake_decky_plugin = types.ModuleType('decky_plugin')
  fake_decky_plugin.logger = types.SimpleNamespace(
    info=lambda *a, **k: None,
    error=lambda *a, **k: None,
    warning=lambda *a, **k: None,
  )
  sys.modules['decky_plugin'] = fake_decky_plugin

if 'plugin_settings' not in sys.modules:
  fake_plugin_settings = types.ModuleType('plugin_settings')
  fake_plugin_settings.get_saved_settings = lambda: {}
  sys.modules['plugin_settings'] = fake_plugin_settings

import intel_rapl
from intel_rapl import (
  resolve_pl2,
  get_pl2_max,
  is_pl2_supported,
  FALLBACK_PL2_MAX_WATTS,
  MSI_WMI,
  RAPL_MMIO,
)


def run():
  failures = []

  cases = [
    # (pl1, mode, offset, pl2_max, pl2_min, expected, description)
    (15, "flat", 7, 30, None, 15, "flat mode regression: PL2 tracks PL1 exactly"),
    (15, "offset", 7, 20, None, 20, "offset+7 clamped at hardware ceiling"),
    (15, "offset", 7, 30, None, 22, "offset+7 under ceiling, unclamped"),
    (15, "max", 7, 30, None, 30, "max mode ignores offset entirely"),
    (25, "offset", 7, 20, None, 25, "PL2 never below PL1 even when pl1 already exceeds pl2_max"),
    (10, "offset", 99, 30, None, 17, "defensive cap: offset silently clamped to 7"),
    (10, "bogus-mode", 7, 30, None, 10, "unrecognized mode falls back to flat-safe behaviour"),
    (30, "offset", 7, 37, 9, 37, "offset+7 at PL1 30 with real hardware ceiling -> 37"),
    (25, "offset", 7, 37, 9, 32, "offset+7 at PL1 25 -> 32"),
    (8, "max", 7, 37, 9, 37, "max mode at PL1 8 -> 37"),
    # regression: pl2_max=None (undiscoverable ceiling) must not trap offset
    # mode at flat -- offset is already self-capped at 7, so it should still
    # apply, clamped only by FALLBACK_PL2_MAX_WATTS
    (23, "offset", 7, None, None, 30, "offset+7 with unknown ceiling -> still applies (23+7=30)"),
    (37, "offset", 7, None, None, FALLBACK_PL2_MAX_WATTS, "offset+7 with unknown ceiling, clamped at fallback (40)"),
    (23, "max", 7, None, None, FALLBACK_PL2_MAX_WATTS, "max mode with unknown ceiling -> fallback (40), not flat"),
    (23, "flat", 7, None, None, 23, "flat mode with unknown ceiling -> still PL1"),
  ]

  for pl1, mode, offset, pl2_max, pl2_min, expected, desc in cases:
    actual = resolve_pl2(pl1, mode, offset, pl2_max, pl2_min)
    status = "OK" if actual == expected else "FAIL"
    if actual != expected:
      failures.append(f"{desc}: resolve_pl2({pl1},{mode!r},{offset},{pl2_max},{pl2_min}) = {actual}, expected {expected}")
    print(f"[{status}] {desc}: got {actual}, expected {expected}")

  # get_pl2_max: regression test for the exact bug seen on real hardware --
  # constraint_1_max_power_uw reading 0 must return None (unknown), NOT fall
  # back to the current value, since current is self-contaminated by flat
  # mode (it was previously forced to equal PL1, so "falling back to it"
  # just rediscovers flat and permanently traps offset/max modes).
  orig_read_int = intel_rapl._read_int
  try:
    intel_rapl._read_int = lambda path: 0 if 'max_power_uw' in (path or '') else 23_000_000
    actual = get_pl2_max(RAPL_MMIO)
    desc = "get_pl2_max returns None (not a self-contaminated current value) when declared max reads 0"
    status = "OK" if actual is None else "FAIL"
    if actual is not None:
      failures.append(f"{desc}: got {actual}, expected None")
    print(f"[{status}] {desc}: got {actual}, expected None")

    intel_rapl._read_int = lambda path: 37_000_000 if 'max_power_uw' in (path or '') else 23_000_000
    actual = get_pl2_max(RAPL_MMIO)
    desc = "get_pl2_max returns the declared value when it's non-zero"
    status = "OK" if actual == 37 else "FAIL"
    if actual != 37:
      failures.append(f"{desc}: got {actual}, expected 37")
    print(f"[{status}] {desc}: got {actual}, expected 37")
  finally:
    intel_rapl._read_int = orig_read_int

  # is_pl2_supported: RAPL doesn't need a discoverable ceiling (offset mode
  # is safe without one); msi-wmi-platform does need real reported headroom.
  supported_cases = [
    (None, None, None, False, "no interface -> unsupported"),
    (MSI_WMI, 37, 30, True, "msi-wmi with real headroom -> supported"),
    (MSI_WMI, 30, 30, False, "msi-wmi with no headroom (pl2_max == pl1_max) -> unsupported"),
    (MSI_WMI, None, 30, False, "msi-wmi with unknown pl2_max -> unsupported"),
  ]
  for interface, pl2_max, pl1_max, expected, desc in supported_cases:
    actual = is_pl2_supported(interface, pl2_max, pl1_max)
    status = "OK" if actual == expected else "FAIL"
    if actual != expected:
      failures.append(f"{desc}: is_pl2_supported({interface},{pl2_max},{pl1_max}) = {actual}, expected {expected}")
    print(f"[{status}] {desc}: got {actual}, expected {expected}")

  # RAPL case needs a real filesystem check (os.path.exists on the PL2 path),
  # so it's tested separately via monkeypatching os.path.exists.
  orig_exists = intel_rapl.os.path.exists
  try:
    intel_rapl.os.path.exists = lambda path: True
    actual = is_pl2_supported(RAPL_MMIO, None, 30)
    desc = "RAPL with unknown pl2_max but a real PL2 write target -> still supported"
    status = "OK" if actual is True else "FAIL"
    if actual is not True:
      failures.append(f"{desc}: got {actual}, expected True")
    print(f"[{status}] {desc}: got {actual}, expected True")

    intel_rapl.os.path.exists = lambda path: False
    actual = is_pl2_supported(RAPL_MMIO, None, 30)
    desc = "RAPL with no PL2 write target at all -> unsupported"
    status = "OK" if actual is False else "FAIL"
    if actual is not False:
      failures.append(f"{desc}: got {actual}, expected False")
    print(f"[{status}] {desc}: got {actual}, expected False")
  finally:
    intel_rapl.os.path.exists = orig_exists

  total = len(cases) + 2 + len(supported_cases) + 2

  if failures:
    print(f"\n{len(failures)} FAILURE(S):")
    for f in failures:
      print(f"  - {f}")
    raise SystemExit(1)

  print(f"\nAll {total} cases passed.")


if __name__ == '__main__':
  run()
