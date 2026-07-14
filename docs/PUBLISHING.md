# Publishing / maintainer guide

How to cut a release and get the widget in front of people. None of this is
required to *use* the tool — it's for the maintainer.

## 1. Cut a release

1. Update `<xbar.version>` in `claude-usage.5m.py` and add a `CHANGELOG.md` entry.
2. Make sure CI is green (`ruff`, `py_compile`, `tests/test_plugin.py`).
3. Tag and push:
   ```bash
   git tag -a v1.2.0 -m "v1.2.0"
   git push origin v1.2.0
   ```
4. Create a GitHub Release from the tag; paste the CHANGELOG section as the
   notes. Attaching `claude-usage.5m.py` as a release asset is optional (the
   installer pulls from the repo, not the asset).

The README's `curl … | bash` one-liner tracks `main`. To let users pin a
version, they can set `CUM_REF`:
```bash
curl -fsSL https://raw.githubusercontent.com/billjoel25/claude-usage-meter/v1.2.0/install.sh | CUM_REF=v1.2.0 bash
```

## 2. Homebrew tap (optional)

The formula lives in this repo at `Formula/claude-usage-meter.rb`. Because the
repo isn't named `homebrew-*`, users tap it with the two-argument form:

```bash
brew tap billjoel25/claude-usage-meter https://github.com/billjoel25/claude-usage-meter
brew install billjoel25/claude-usage-meter/claude-usage-meter
```

After each release, update the formula's `tag:` and `revision:` to the new tag's
commit SHA (`git rev-parse v1.2.0`). Homebrew can't drop a file into a user's
SwiftBar folder, so the formula installs the script into its prefix and prints a
`caveats` message with the exact symlink command — this is why the `curl`
installer is the primary, simpler path.

## 3. SwiftBar / xbar plugin catalog

SwiftBar's own catalog repo (`swiftbar/swiftbar-plugins`) is **archived**. The
live, maintained catalog for both xbar and SwiftBar (they share the metadata
format) is **[`matryer/xbar-plugins`](https://github.com/matryer/xbar-plugins)**,
which powers the xbar.app plugin browser.

Checklist to submit:

1. Fork `matryer/xbar-plugins`.
2. Copy `claude-usage.5m.py` into a category directory (e.g. `Dev/` or
   `System/`). Keep the filename's `.5m.` cadence segment.
3. The metadata header is already compliant (`<xbar.title>`, `<xbar.version>`,
   `<xbar.author>`, `<xbar.author.github>`, `<xbar.desc>`, `<xbar.dependencies>`,
   `<xbar.abouturl>`). **Add `<xbar.image>`** pointing at a hosted screenshot —
   the catalog shows it on the plugin's page:
   ```python
   # <xbar.image>https://raw.githubusercontent.com/billjoel25/claude-usage-meter/main/docs/screenshot.png</xbar.image>
   ```
4. Open a PR against `matryer/xbar-plugins`. Review checks the metadata, that the
   script is self-contained, and that it runs. Common rejection reasons: missing
   image/desc, secrets committed, or network calls without a clear purpose.
5. Once merged it appears at xbar.app and in SwiftBar's **Get Plugins…** browser.

> A real PNG screenshot at `docs/screenshot.png` is the one asset still worth
> adding — the README currently uses an ASCII mock, which the catalog can't show.
