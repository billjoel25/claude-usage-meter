# Claude Plan Usage

A tiny macOS **menu-bar** widget that shows how much of your **Claude plan** you've
used — the rolling **5-hour** window and the **weekly** limit — at a glance, for one
or more accounts.

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

- **Sign in with Claude** — one click, browser login, no CLI. Add several accounts.
- **Pick your number** — the menu bar shows the **5-hour window** by default; switch
  it to weekly, both (`42/90%`), or the worst window via dropdown → **Menu bar shows**.
  A `⚠` appears whenever a window you're *not* showing (weekly, Opus…) is in the red.
- **Pure Python 3** — no pip installs, no build step.
- **Private** — your token is stored locally and sent only to `api.anthropic.com`
  over HTTPS. Nothing goes to any third party.
- Color turns amber → red as a window nears its limit; reset countdowns; per-model
  weekly limits (`seven_day_opus` / `seven_day_sonnet`) and extra-usage credits when
  your plan reports them.

## Install

Requires [SwiftBar](https://github.com/swiftbar/SwiftBar) (or xbar).

```bash
git clone https://github.com/billjoel25/claude-usage-meter.git
cd claude-usage-meter
bash install.sh
brew install --cask swiftbar   # if you don't have it
```

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

## How it works

It reads Anthropic's usage endpoint (`GET https://api.anthropic.com/api/oauth/usage`)
with your OAuth token — the same numbers Claude Code's `/usage` shows. Sign-in uses
the standard OAuth 2.0 Authorization-Code + PKCE flow.

The refresh cadence is the `.5m.` in the filename (every 5 min); results are cached
~3 min so manual refreshes don't trip the endpoint's rate limit.

> ⚠️ `/api/oauth/usage` and the sign-in flow use **unofficial** Anthropic endpoints
> (the same ones Claude Code uses). They're read-only and widely used by community
> tools, but Anthropic could change them. If numbers or sign-in break, that's the
> first thing to check.

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
  ]
}
```

| key                | what it does                                                     |
| ------------------ | ---------------------------------------------------------------- |
| `token_cmd`        | a shell command that prints a bare bearer token                  |
| `token`            | a literal token (discouraged — sensitive)                        |
| `credentials_file` | path to a Claude Code `.credentials.json`                        |
| `keychain_service` | macOS Keychain generic-password service name                     |

## Tuning

The menu-bar number is chosen from the dropdown (**Menu bar shows** → 5-hour /
weekly / both / worst), stored as `"menu_bar"` in the config file.

For the rest, edit the constants near the top of `claude-usage.5m.py`:

- `AMBER_AT` / `RED_AT` — the % thresholds for yellow/red.
- `CACHE_TTL` — cache lifetime in seconds (keep ≥ 180 to avoid 429s).
- Rename the file's `.5m.` segment to change the refresh interval.

## Troubleshooting

- **"not logged in"** — click **➕ Add Claude account** and sign in.
- **"sign-in expired"** — sign out and add the account again.
- **"429 — rate limited"** — you're polling too hard; it recovers next tick.
- **Widget missing from the menu bar** — it's usually hidden behind the notch on a
  full menu bar. Free up space, or use a menu-bar manager to reveal it.
- **Numbers frozen** — dropdown → **Force refresh (clear cache)**.

## Prior art

Other tools in this space worth a look: the native apps
[ClaudeMeter](https://claude-meter.com/), [Claude God](https://claudegod.app/),
[ClaudeUsageBar](https://www.claudeusagebar.com/); and the SwiftBar/xbar plugins
[claude-quota](https://github.com/grzegorz-raczek-unit8/claude-quota) and
[Claude Usage Barometer](https://www.atlasassociates.io/en/claude-usage-barometer/).

## License

MIT — see [LICENSE](LICENSE).
