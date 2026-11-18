# Security

## What this tool touches

- It sends your Claude OAuth **bearer token** only to `api.anthropic.com` (the
  usage endpoint) and to Anthropic's OAuth token endpoint (to sign in and to
  refresh). Nothing is sent to any third party.
- Tokens are stored locally under `~/.config/claude-usage-meter/accounts/` with
  file permissions `600`. An auto-detected Claude Code login is read from the
  macOS Keychain or `~/.claude/.credentials.json` and is never copied elsewhere.
- To notify you if your org moves off Team, it reads one field —
  `oauthAccount.organizationType` — from `~/.claude.json`. Only that value is
  kept (in `~/.config/claude-usage-meter/plan-state.json`), and it only ever
  leaves the file as the text of a local macOS notification.
- The widget makes no other network calls and has no telemetry.

## Unofficial endpoints — read this

The plan-usage endpoint (`GET /api/oauth/usage`) and the sign-in flow use
**unofficial** Anthropic endpoints — the same ones the Claude Code CLI uses.
They are read-only and widely used by community tools, but they are not a
published, supported API and Anthropic can change or remove them at any time.
If numbers or sign-in stop working, that is the first thing to suspect. Use of
these endpoints is at your own discretion; this project is not affiliated with
or endorsed by Anthropic.

## Reporting a vulnerability

Please **don't** open a public issue for anything sensitive (e.g. a way to leak
a token). Instead use GitHub's private
[security advisories](https://github.com/billjoel25/claude-usage-meter/security/advisories/new)
for this repository. For non-sensitive bugs, a normal issue is fine.

There are no formal support guarantees — this is a hobby tool under the MIT
license, provided "as is" (see [LICENSE](LICENSE)).
