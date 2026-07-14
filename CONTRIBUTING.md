# Contributing

Thanks for your interest! This is a small, single-file tool and aims to stay that way.

## Ground rules

- **Pure Python 3, standard library only.** No pip installs, no build step — the
  whole point is that it drops into SwiftBar and runs. Don't add runtime deps.
- The plugin is `claude-usage.5m.py`. The `.5m.` tells SwiftBar/xbar to run it
  every 5 minutes; keep that unless you have a reason to change the cadence.
- Keep the menu-bar output valid [SwiftBar/xbar format](https://github.com/swiftbar/SwiftBar#plugin-api)
  (`text | key=value …`, `---` separators).

## Develop & test

```bash
# lint (matches CI)
pipx run ruff check claude-usage.5m.py tests/test_plugin.py

# compile check
python3 -m py_compile claude-usage.5m.py

# tests — no dependencies
python3 tests/test_plugin.py

# see the actual dropdown without touching your real config/login
HOME="$(mktemp -d)" CLAUDE_USAGE_METER_HOME="$(mktemp -d)" python3 claude-usage.5m.py
```

CI runs the same three checks (`.github/workflows/ci.yml`) on every push and PR.

## Adding a test

`tests/test_plugin.py` is a plain-`assert` file with a tiny runner — add a
`def test_…()` and it's picked up automatically. Use the `_isolate(tmp)` helper
to redirect the module's filesystem paths at a throwaway directory so tests never
read or write your real config or tokens.

## Pull requests

- One focused change per PR; update `CHANGELOG.md` under a new heading.
- Bump `<xbar.version>` in the plugin header when behavior changes.
- Note anything that touches the sign-in flow or the usage endpoint — those use
  unofficial Anthropic endpoints (see [SECURITY.md](SECURITY.md)).
