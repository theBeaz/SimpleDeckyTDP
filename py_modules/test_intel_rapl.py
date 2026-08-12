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

from intel_rapl import resolve_pl2


def run():
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
  ]

  failures = []
  for pl1, mode, offset, pl2_max, pl2_min, expected, desc in cases:
    actual = resolve_pl2(pl1, mode, offset, pl2_max, pl2_min)
    status = "OK" if actual == expected else "FAIL"
    if actual != expected:
      failures.append(f"{desc}: resolve_pl2({pl1},{mode!r},{offset},{pl2_max},{pl2_min}) = {actual}, expected {expected}")
    print(f"[{status}] {desc}: got {actual}, expected {expected}")

  if failures:
    print(f"\n{len(failures)} FAILURE(S):")
    for f in failures:
      print(f"  - {f}")
    raise SystemExit(1)

  print(f"\nAll {len(cases)} resolve_pl2 cases passed.")


if __name__ == '__main__':
  run()
