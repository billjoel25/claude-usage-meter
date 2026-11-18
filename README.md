# Claude Plan Usage

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/billjoel25/claude-usage-meter?sort=semver)](https://github.com/billjoel25/claude-usage-meter/releases)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey)
[![CI](https://github.com/billjoel25/claude-usage-meter/actions/workflows/ci.yml/badge.svg)](https://github.com/billjoel25/claude-usage-meter/actions/workflows/ci.yml)

A tiny macOS **menu-bar** widget that shows how much of your **Claude plan** you've
used — your **current session** (the rolling 5-hour window) at a glance, with the
weekly and per-model limits one click away — for one or more accounts.

It shows **plan usage**: the exact percentages Claude's own `/usage` shows and
enforces on **Pro / Max / Team** — **not** API dollar cost.

```
✳ P 96%  · W 40%         ← menu bar (always the current session)
────────────────────────
personal
  session [█████████░] 96%  resets in 47m
  weekly  [█████░░░░░] 54%  resets in 4d0h
    · Opus [█████████░] 91%  resets in 4d0h
work
  session [████░░░░░░] 40%  resets in 3h10m
  weekly  [████████░░] 80%  resets in 4d0h
────────────────────────
Accounts
  ✓ personal              ← click to hide it from the menu bar
     ↓ move down
  ✓ work
     ↑ move up
```

- **Sign in with Claude** — one click, browser login, no CLI. Add several accounts.
- **Choose which accounts appear, and in what order** — dropdown → **Accounts**: click
  one to show or hide its number in the menu bar, or move it up/down. A hidden account
  keeps its full section in the dropdown, so you still see its numbers on a click.
- **Current session only, up top** — the menu bar is always the rolling 5-hour
  session percentage; a higher weekly or Opus number never takes its place. Open the
  dropdown for the weekly cap, per-model caps, and extra-usage credits, where each
  account's status dot still turns red if *any* of its windows is near the ceiling.
- **Plan-change notice** — if your org ever moves off Team (to Enterprise, where
  admins may be able to read your Claude Code sessions), you get one macOS
  notification. Nothing else about it shows anywhere.
- **Pure Python 3** — no pip installs, no build step.
- **Private** — your token is stored locally and sent only to `api.anthropic.com`
  over HTTPS. Nothing goes to any third party.
- Plain black text — no traffic-light colors on your usage, however close a window
  gets. The percentage and its reset countdown say how near you are and when it
  clears; color on top of that only added worry. (Want green/amber back? See
  [Tuning](#tuning).) Per-model weekly limits (`seven_day_opus` / `seven_day_sonnet`)
  and extra-usage credits appear when your plan reports them.

## Install

You need [SwiftBar](https://github.com/swiftbar/SwiftBar) (or xbar):

```bash
brew install --cask swiftbar
```

**One line** (inspect the [script](install.sh) first if you like):

```bash
curl -fsSL https://raw.githubusercontent.com/billjoel25/claude-usage-meter/main/install.sh | bash
```

<details>
<summary>Or from a clone</summary>

```bash
git clone https://github.com/billjoel25/claude-usage-meter.git
cd claude-usage-meter
bash install.sh
```
</details>

<details>
<summary>Or via Homebrew (optional)</summary>

```bash
brew tap billjoel25/claude-usage-meter https://github.com/billjoel25/claude-usage-meter
brew install billjoel25/claude-usage-meter/claude-usage-meter
```

Homebrew can't drop the plugin into your SwiftBar folder, so it prints a one-line
`ln -sf …` symlink command to finish — the `curl` installer above is simpler.
</details>

Open SwiftBar and set its **Plugin Folder** to the path the installer prints. The
widget appears within a few seconds.

## Sign in

Click the **Claude icon** in the menu bar → **➕ Add Claude account**. A Terminal
window opens and walks you through it:

1. Your browser opens to Claude's sign-in page — log in and approve.
2. Claude shows you a short code (like `ABC123#XYZ`); paste it back into the Terminal.
3. Name the account (or accept the default) — done.

Add another account by clicking **➕ Add Claude account** again and signing in with
the other login. To remove one, open its section in the dropdown → **↳ sign out**.

Your access + refresh tokens are stored locally under
`~/.config/claude-usage-meter/accounts/` (file permissions `600`) and refreshed
automatically. On first read, macOS may ask to let SwiftBar use the Keychain — click
**Always Allow**.

## Uninstall

```bash
bash uninstall.sh          # remove the plugin + cache (keeps your login)
bash uninstall.sh --all    # also remove config + stored account tokens
```

## How it works

It reads Anthropic's usage endpoint (`GET https://api.anthropic.com/api/oauth/usage`)
with your OAuth token — the same numbers Claude Code's `/usage` shows. Sign-in uses
the standard OAuth 2.0 Authorization-Code + PKCE flow.

The refresh cadence is the `.5m.` in the filename (every 5 min); results are cached
~3 min so manual refreshes don't trip the endpoint's rate limit.

> ⚠️ `/api/oauth/usage` and the sign-in flow use **unofficial** Anthropic endpoints
> (the same ones Claude Code uses). They're read-only and widely used by community
> tools, but Anthropic could change them. If numbers or sign-in break, that's the
> first thing to check. See [SECURITY.md](SECURITY.md).

## Plan-change notice

Claude Code sessions on a **Team** plan can't be read by org admins; on **Enterprise**
with the Compliance API enabled, they can — from the day it's switched on, not
retroactively. So the widget watches one field, `oauthAccount.organizationType` in
`~/.claude.json` (the server keeps it current), and posts a single macOS notification
the moment it moves off `claude_team`. Nothing shows in the menu bar or the dropdown.

The string an Enterprise org reports isn't known, so it doesn't look for one: any move
off Team counts, and the notification quotes exactly what it read. A file it can't read
is skipped rather than reported. The last value seen lives in
`~/.config/claude-usage-meter/plan-state.json`.

The notification comes from SwiftBar (or Script Editor, without SwiftBar). To check
that macOS will actually show it, run this once:

```bash
python3 "$(defaults read com.ameba.SwiftBar PluginDirectory)/claude-usage.5m.py" notify-test
```

No banner? Allow notifications for that app in System Settings → Notifications.

## Advanced: use an existing Claude Code login instead

If you already use the **Claude Code CLI**, the widget auto-detects its login (macOS
Keychain, or `~/.claude/.credentials.json`) — no sign-in needed. For a second CLI
account under its own config dir:

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-work" claude   # log in with the 2nd account
```

Then point the widget at that login's (hashed) Keychain entry via the config file
below. Find the service name with:

```bash
DIR="$HOME/.claude-work"
for D in "$DIR" "$DIR/"; do
  for H in "$(printf '%s' "$D" | shasum -a 256 | cut -c1-8)" "$(printf '%s' "$D" | md5 | cut -c1-8)"; do
    security find-generic-password -s "Claude Code-credentials-$H" >/dev/null 2>&1 \
      && echo "Keychain service: Claude Code-credentials-$H"
  done
done
```

### Config

Optional file at `~/.config/claude-usage-meter/config.json` (only needed for the
advanced CLI/Keychain path; signed-in accounts don't need it). One entry per account;
each account tries its token sources in order:

```json
{
  "accounts": [
    { "label": "personal", "keychain_service": "Claude Code-credentials",
      "credentials_file": "~/.claude/.credentials.json" },
    { "label": "work", "keychain_service": "Claude Code-credentials-XXXXXXXX" }
  ],
  "accounts_display": [
    { "label": "work", "menu_bar": true },
    { "label": "personal", "menu_bar": false }
  ]
}
```

| key                | what it does                                                     |
| ------------------ | ---------------------------------------------------------------- |
| `token_cmd`        | a shell command that prints a bare bearer token                  |
| `token`            | a literal token (discouraged — sensitive)                        |
| `credentials_file` | path to a Claude Code `.credentials.json`                        |
| `keychain_service` | macOS Keychain generic-password service name                     |

`accounts_display` is the dropdown → **Accounts** submenu written down: the list order
is the display order (menu bar *and* dropdown sections), and `menu_bar: false` keeps an
account out of the menu bar while leaving its section in the dropdown. It covers
signed-in accounts too, not just the `accounts` above. Everything about it is optional —
accounts it doesn't mention follow at the end and are shown, so without the key nothing
changes. A bare `"work"` string works as an order-only entry, and a label that no longer
matches an account is ignored.

## Tuning

The menu-bar number is always the current session (the rolling 5-hour window) — there
is nothing to configure. Earlier versions had a **Menu bar shows** selector backed by a
`"menu_bar"` config key; both are gone, and a leftover `"menu_bar"` key is ignored.

Usage rows are plain black (white in dark mode) by default. To color them by how full
they are instead, set `"colors": "status"` in the config file — green below half,
amber above it.

For the rest, edit the constants near the top of `claude-usage.5m.py`:

- `AMBER_AT` — in `status` colors, the % at which a window turns amber (default 50).
- `RED_AT` — in `status` colors, off by default (`None`): nothing goes red. Set it
  (e.g. `85`) for a red tier near the ceiling.
- `CACHE_TTL` — cache lifetime in seconds (keep ≥ 180 to avoid 429s).
- `STALE_MAX` — how long a cached reading may stand in for a live one when a fetch
  fails (default 30 min). Past it the numbers are dropped and the cache file deleted.
- Rename the file's `.5m.` segment to change the refresh interval.

## Troubleshooting

- **"not logged in"** — click **➕ Add Claude account** and sign in.
- **"sign-in expired"** — sign out and add the account again.
- **"429 — rate limited"** — you're polling too hard; it recovers next tick. The
  cached numbers keep showing meanwhile, which is exactly what they're for.
- **Widget missing from the menu bar** — it's usually hidden behind the notch on a
  full menu bar. Free up space, or use a menu-bar manager to reveal it.
- **Numbers frozen** — they shouldn't stay that way on their own. When a fetch keeps
  failing, the cached reading stands in for up to `STALE_MAX` (30 min) and then clears
  itself, so the account drops to an error rather than showing a number that's quietly
  wrong. A cached window that has passed its own reset time is dropped immediately,
  whatever its age. **Force refresh (clear cache)** is still there if you'd rather not
  wait — but you shouldn't need it.

## Contributing

Bug reports and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). It's a single
pure-Python-3 file with a dependency-free test suite (`python3 tests/test_plugin.py`)
and CI. Release/publishing steps live in [docs/PUBLISHING.md](docs/PUBLISHING.md).

## Prior art

Other tools in this space worth a look: the native apps
[ClaudeMeter](https://claude-meter.com/), [Claude God](https://claudegod.app/),
[ClaudeUsageBar](https://www.claudeusagebar.com/); and the SwiftBar/xbar plugins
[claude-quota](https://github.com/grzegorz-raczek-unit8/claude-quota) and
[Claude Usage Barometer](https://www.atlasassociates.io/en/claude-usage-barometer/).

## License

MIT — see [LICENSE](LICENSE).
