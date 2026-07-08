# Claude Plan Usage

A tiny macOS **menu-bar** widget that shows how much of your **Claude plan** you've
used — the rolling **5-hour** window and the **weekly** limit — at a glance, for one
or more accounts (personal, work, etc.).

It shows **plan usage**: the exact percentages Claude's own `/usage` shows and
enforces on **Pro / Max / Team** — **not** API dollar cost.

```
✳ P 96% · L 80%          ← menu bar (P/L = per-account initials)
────────────────────────
personal
  5-hour  [█████████░] 96%  resets in 47m
  weekly  [█████░░░░░] 54%  resets in 4d0h
    · Opus [█████████░] 91%  resets in 4d0h
work
  5-hour  [████░░░░░░] 40%  resets in 3h10m
  weekly  [████████░░] 80%  resets in 4d0h
```

- **Pure Python 3** — no pip installs, no build step.
- **Private** — your token is read locally and sent only to `api.anthropic.com` over
  HTTPS. Nothing goes to any third party.
- **Multi-account** — show several Claude logins side by side.
- Color turns amber → red as a window nears its limit; reset countdowns; per-model
  weekly limits (`seven_day_opus` / `seven_day_sonnet`) and extra-usage credits when
  your plan reports them.

## How it works

It reads Anthropic's usage endpoint (`GET https://api.anthropic.com/api/oauth/usage`)
using the OAuth token from your existing **Claude Code** login — the same source
Claude Code's `/usage` uses. On macOS the token lives in the Keychain; on Linux/WSL
it's `~/.claude/.credentials.json`.

> ⚠️ `/api/oauth/usage` is an **internal** endpoint, not a documented public API.
> It's read-only and it's what the community usage widgets use, but Anthropic could
> change it. If the numbers go blank, that's the first thing to check.

## Install

Requires [SwiftBar](https://github.com/swiftbar/SwiftBar) (or xbar) and the Claude
Code CLI (that's what mints the token this reads).

```bash
git clone https://github.com/billjoel25/claude-usage-meter.git
cd claude-usage-meter
bash install.sh
brew install --cask swiftbar   # if you don't have it
```

Open SwiftBar and set its **Plugin Folder** to the path the installer prints. The
widget appears within ~5 min (or SwiftBar → Refresh). On first run, macOS asks to let
SwiftBar read your Claude login from the Keychain — click **Always Allow**.

The refresh cadence is the `.5m.` in the filename (every 5 min); results are also
cached ~3 min so manual refreshes don't trip the endpoint's rate limit.

## Multiple accounts

Claude Code keeps one login per **config directory**, and on macOS derives a separate
(hashed) Keychain entry for each. To run a second account beside your main one:

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-work" claude   # log in with the 2nd account
```

That creates an independent, auto-refreshing login without disturbing your main one.
To point the widget at it, find that login's Keychain service name:

```bash
DIR="$HOME/.claude-work"
for D in "$DIR" "$DIR/"; do
  for H in "$(printf '%s' "$D" | shasum -a 256 | cut -c1-8)" "$(printf '%s' "$D" | md5 | cut -c1-8)"; do
    security find-generic-password -s "Claude Code-credentials-$H" >/dev/null 2>&1 \
      && echo "Keychain service: Claude Code-credentials-$H"
  done
done
```

Add it to your config (see below) as the second account's `keychain_service`.

## Config

Optional file at `~/.config/claude-usage-meter/config.json` (the installer seeds one
from `config.example.json`). One entry per account; the widget tries each token
source in order and shows whichever accounts resolve:

```json
{
  "accounts": [
    { "label": "personal", "keychain_service": "Claude Code-credentials",
      "credentials_file": "~/.claude/.credentials.json" },
    { "label": "work", "keychain_service": "Claude Code-credentials-XXXXXXXX" }
  ]
}
```

Per-account keys (first that resolves wins):

| key                | what it does                                                       |
| ------------------ | ----------------------------------------------------------------- |
| `token_cmd`        | a shell command that prints a bare bearer token (most flexible)   |
| `token`            | a literal token (discouraged — sensitive)                         |
| `credentials_file` | path to a Claude Code `.credentials.json`                         |
| `keychain_service` | macOS Keychain generic-password service name                      |

Config is also looked up at `$CLAUDE_USAGE_METER_CONFIG` and, for backward
compatibility, `~/.clarity/claude-usage.json`.

## Tuning

Edit the constants near the top of `claude-usage.5m.py`:

- `AMBER_AT` / `RED_AT` — the % thresholds for yellow/red.
- `CACHE_TTL` — cache lifetime in seconds (keep ≥ 180 to avoid 429s).
- Rename the file's `.5m.` segment to change the refresh interval.

## Troubleshooting

- **"not logged in"** — run `claude` once for that account.
- **"token expired" / 401** — re-run `claude` to refresh the login.
- **"429 — rate limited"** — you're polling too hard; it recovers next tick. Don't set
  the refresh below a few minutes.
- **Widget missing from the menu bar** — it's usually hidden behind the notch on a full
  menu bar. Free up space, or use a menu-bar manager to reveal it.
- **Numbers frozen** — dropdown → **Force refresh (clear cache)**.

## Prior art

Other tools in this space (worth a look): the native apps
[ClaudeMeter](https://claude-meter.com/), [Claude God](https://claudegod.app/),
[ClaudeUsageBar](https://www.claudeusagebar.com/); and the SwiftBar/xbar plugins
[claude-quota](https://github.com/grzegorz-raczek-unit8/claude-quota) and
[Claude Usage Barometer](https://www.atlasassociates.io/en/claude-usage-barometer/).

## License

MIT — see [LICENSE](LICENSE).
