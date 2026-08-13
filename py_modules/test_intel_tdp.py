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

import intel_tdp
from intel_tdp import resolve_pl2, is_pl2_supported, is_available, apply_pl1_pl2


def run():
  failures = []

  cases = [
    # (pl1, mode, offset, pl2_min, pl2_max, expected, description)
    (15, "flat", 7, 9, 30, 15, "flat mode regression: PL2 tracks PL1 exactly"),
    (15, "offset", 7, 9, 20, 20, "offset+7 clamped at hardware ceiling"),
    (15, "offset", 7, 9, 30, 22, "offset+7 under ceiling, unclamped"),
    (15, "max", 7, 9, 30, 30, "max mode ignores offset entirely"),
    (25, "offset", 7, 9, 20, 25, "PL2 never below PL1 even when pl1 already exceeds pl2_max"),
    (10, "offset", 99, 9, 30, 17, "defensive cap: offset silently clamped to 7"),
    (10, "bogus-mode", 7, 9, 30, 10, "unrecognized mode falls back to flat-safe behaviour"),
    (30, "offset", 7, 9, 37, 37, "offset+7 at PL1 30 with real hardware ceiling -> 37"),
    (25, "offset", 7, 9, 37, 32, "offset+7 at PL1 25 -> 32"),
    (8, "max", 7, 9, 37, 37, "max mode at PL1 8 -> 37"),
    (3, "offset", 7, 9, 37, 10, "offset respects pl2_min floor when pl1+offset is still below it (3+7=10 >= 9)"),
  ]

  for pl1, mode, offset, pl2_min, pl2_max, expected, desc in cases:
    actual = resolve_pl2(pl1, mode, offset, pl2_min, pl2_max)
    status = "OK" if actual == expected else "FAIL"
    if actual != expected:
      failures.append(f"{desc}: resolve_pl2({pl1},{mode!r},{offset},{pl2_min},{pl2_max}) = {actual}, expected {expected}")
    print(f"[{status}] {desc}: got {actual}, expected {expected}")

  # is_available / is_pl2_supported: gate entirely on the firmware-attribute
  # directories existing -- no RAPL involved at all.
  orig_isdir = intel_tdp.os.path.isdir
  try:
    intel_tdp.os.path.isdir = lambda path: False
    actual = is_available()
    desc = "is_available() False when firmware-attribute dirs are absent"
    status = "OK" if actual is False else "FAIL"
    if actual is not False:
      failures.append(f"{desc}: got {actual}")
    print(f"[{status}] {desc}: got {actual}")

    actual = is_pl2_supported()
    desc = "is_pl2_supported() False when interface unavailable"
    status = "OK" if actual is False else "FAIL"
    if actual is not False:
      failures.append(f"{desc}: got {actual}")
    print(f"[{status}] {desc}: got {actual}")

    actual = apply_pl1_pl2(23)
    desc = "apply_pl1_pl2() refuses to write (returns False) when interface unavailable -- no RAPL fallback"
    status = "OK" if actual is False else "FAIL"
    if actual is not False:
      failures.append(f"{desc}: got {actual}")
    print(f"[{status}] {desc}: got {actual}")
  finally:
    intel_tdp.os.path.isdir = orig_isdir

  # is_pl2_supported with a real (mocked) headroom scenario
  orig_isdir = intel_tdp.os.path.isdir
  orig_read_int = intel_tdp._read_int
  try:
    intel_tdp.os.path.isdir = lambda path: True
    values = {
      intel_tdp._pl1_max_path(): 30,
      intel_tdp._pl2_max_path(): 37,
    }
    intel_tdp._read_int = lambda path: values.get(path)
    actual = is_pl2_supported()
    desc = "is_pl2_supported() True when pl2_max (37) > pl1_max (30)"
    status = "OK" if actual is True else "FAIL"
    if actual is not True:
      failures.append(f"{desc}: got {actual}")
    print(f"[{status}] {desc}: got {actual}")

    values = {
      intel_tdp._pl1_max_path(): 30,
      intel_tdp._pl2_max_path(): 30,
    }
    actual = is_pl2_supported()
    desc = "is_pl2_supported() False when pl2_max == pl1_max (no real headroom)"
    status = "OK" if actual is False else "FAIL"
    if actual is not False:
      failures.append(f"{desc}: got {actual}")
    print(f"[{status}] {desc}: got {actual}")
  finally:
    intel_tdp.os.path.isdir = orig_isdir
    intel_tdp._read_int = orig_read_int

  # apply_pl1_pl2 write-order regression: raising flat (10,10) -> (20,20)
  # must never pass through an intermediate PL2<PL1 state. This is exactly
  # the scenario where the directive's literal "raising: PL1 then PL2" rule
  # fails (intermediate would be 20/10); verify our write order avoids it.
  orig_isdir = intel_tdp.os.path.isdir
  orig_read_int = intel_tdp._read_int
  orig_write_verify = intel_tdp._write_verify
  try:
    intel_tdp.os.path.isdir = lambda path: True
    state = {intel_tdp._pl1_current_path(): 10, intel_tdp._pl2_current_path(): 10}
    ranges = {
      intel_tdp._pl1_min_path(): 8, intel_tdp._pl1_max_path(): 30,
      intel_tdp._pl2_min_path(): 9, intel_tdp._pl2_max_path(): 37,
    }
    intel_tdp._read_int = lambda path: state.get(path, ranges.get(path))

    write_order = []

    def fake_write_verify(path, value_w):
      write_order.append((path, value_w))
      state[path] = value_w
      return value_w

    intel_tdp._write_verify = fake_write_verify

    # force offset mode, PL1 10->20 -> PL2 should follow to 27 (20+7);
    # intel_tdp bound its own `get_saved_settings` reference at import time
    # (`from plugin_settings import get_saved_settings`), so patch that
    # binding directly rather than the source module's attribute.
    orig_get_saved_settings = intel_tdp.get_saved_settings
    intel_tdp.get_saved_settings = lambda: {"pl2Mode": "offset", "pl2Offset": 7}
    try:
      apply_pl1_pl2(20)  # pl1 10->20, pl2 10->27 (20+7)
    finally:
      intel_tdp.get_saved_settings = orig_get_saved_settings

    desc = "raising 10/10 -> 20/27 writes PL2 before PL1 (never exposes 20/10)"
    order_ok = write_order and write_order[0][0] == intel_tdp._pl2_current_path()
    values_ok = state.get(intel_tdp._pl1_current_path()) == 20 and state.get(intel_tdp._pl2_current_path()) == 27
    status = "OK" if order_ok and values_ok else "FAIL"
    if status == "FAIL":
      failures.append(f"{desc}: write order was {write_order}, final state {state}")
    print(f"[{status}] {desc}: write order was {write_order}, final state {state}")
  finally:
    intel_tdp.os.path.isdir = orig_isdir
    intel_tdp._read_int = orig_read_int
    intel_tdp._write_verify = orig_write_verify

  if failures:
    print(f"\n{len(failures)} FAILURE(S):")
    for f in failures:
      print(f"  - {f}")
    raise SystemExit(1)

  print(f"\nAll checks passed.")


if __name__ == '__main__':
  run()
