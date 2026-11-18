# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Plan-change notification.** If your Claude org ever moves off Team — to
  Enterprise, where admins may be able to read your Claude Code sessions — you get
  a single macOS notification, sent through SwiftBar. Nothing shows in the menu bar
  or the dropdown, before or after. It watches `oauthAccount.organizationType` in
  `~/.claude.json` and fires on any move off `claude_team`, quoting what it read,
  since the string an Enterprise org reports isn't known. A file it can't read is
  skipped, never reported as a change. `notify-test` checks that macOS will show it.
- **Account order and menu-bar on/off.** A new **Accounts** submenu in the
  dropdown: click an account to show or hide its number in the menu bar, or move
  it up/down. The order applies to the menu bar *and* the dropdown sections. A
  hidden account keeps its full section in the dropdown — usage rows, reset
  times, sign out — marked *hidden from menu bar*, so nothing is lost from view.
  Choices persist as `accounts_display` in the config file, an ordered list of
  `{"label": …, "menu_bar": true|false}` that is equally editable by hand and
  covers signed-in accounts as well as hand-configured ones. Accounts it doesn't
  mention follow at the end and are shown, so the key stays optional.

### Changed
- **Usage is plain black text.** No traffic-light colors on the rows, the bars, the
  account header or its error line, however close a window is to its limit — a
  weekly window at 85% with a day and a half still to run had lit the dropdown up
  like an alarm, when the number and its reset countdown already say exactly how
  close you are. The color is set explicitly (black, or white in dark mode), since
  SwiftBar draws items without an action as disabled gray. For the old look, set
  `"colors": "status"`: green below half, amber above, and red only if `RED_AT` is
  set — it now defaults to `None`.
- **The cache expires and clears itself.** A failed fetch is still carried by the
  last good reading — but only for `STALE_MAX` (30 min), and never past the reset
  time the reading itself carries: a window that has already rolled over makes its
  number wrong, not merely old. Beyond that the numbers are dropped *and the cache
  file deleted*, so the account falls back to an error rather than showing a
  confident, stale percentage in the menu bar indefinitely. **Force refresh (clear
  cache)** remains, but is no longer something you have to remember to click. A
  cache file that won't parse is now cleaned up the same way, and signing an
  account back in drops its old cache so a re-add starts clean.
- **The menu bar now shows only your current session** — the rolling 5-hour window.
  A higher weekly or per-model (Opus/Sonnet) number no longer replaces it, and the
  **⚠** cross-window marker is gone, so the number up top is always the one window.
  The dropdown is unchanged: it still lists the weekly cap, per-model caps and
  extra-usage credits, and each account's status dot still reflects the worst of
  them, so a limit can't max out entirely unseen.
- The dropdown's `5-hour` row is now labelled `session`, matching `/usage`.

### Removed
- The **Menu bar shows** selector (weekly / both / worst) and its `set-display`
  action — with the menu bar fixed to the current session there is nothing to pick.
  The `"menu_bar"` config key is no longer read; a leftover one is ignored, not
  rewritten, and new starter configs omit it.

### Fixed
- **A rejected token now heals itself where it can.** On a 401 the widget forces
  one token refresh and retries before reporting anything — an access token can be
  dead while the refresh token behind it still works, which previously meant a
  needless sign-out-and-re-add. If that doesn't take, the stale cache for the
  account is cleared rather than left standing. The retry is skipped when the
  refresh returns the same token, so a genuinely dead account costs no extra
  request per tick.

## [1.2.0] - 2026-07-14

### Added
- **Menu-bar window selector.** The menu bar shows the **5-hour** window by
  default; a new dropdown submenu, **Menu bar shows**, switches it to weekly,
  both (`42/90%`), or the worst window. The choice persists as `"menu_bar"` in
  the config file.
- A **⚠** marker is appended to the menu-bar number whenever a window you are
  *not* showing (weekly, Opus…) is at or above the red threshold, so a limit
  can't max out unseen.
- **One-line install:** `install.sh` now also runs standalone via
  `curl … | bash`, downloading the plugin and starter config when it isn't run
  from a clone.
- **`uninstall.sh`** for clean removal (keeps your login unless `--all`).
- Continuous integration (ruff + `py_compile` + a dependency-free test suite),
  a `CHANGELOG`, `CONTRIBUTING`, `SECURITY`, and maintainer `PUBLISHING` guides,
  an optional Homebrew formula, and issue templates.

### Fixed
- The menu-bar summary and per-account status dot now reflect **per-model
  (Opus/Sonnet) weekly caps** — previously they used only the 5-hour and overall
  weekly windows, so they could read amber/green while Opus was already maxed.
- A second **sign-in no longer silently overwrites a different account** that
  happens to map to the same file (e.g. two logins sharing an email local-part).
- Fresh installs show the **"Not signed in yet"** welcome again instead of
  placeholder "not logged in" rows; existing Claude Code logins are still
  auto-detected.
- Menu actions (sign out, force refresh, edit config) **quote their paths**, so
  a space in the home directory no longer breaks them.
- Expiry / 401 messages are tailored per account kind (signed-in accounts are
  told to re-add, not to run `claude`).
- Guarded against a non-dict API payload; a real config file is created on first
  run so "Edit config file" always opens something.

## [1.1.0] - initial public "Sign in with Claude" release

### Added
- **Sign in with Claude** — browser-based OAuth (Authorization Code + PKCE), no
  Claude Code CLI required; multiple accounts; tokens stored locally and
  auto-refreshed.
- Per-model weekly limits (`seven_day_opus` / `seven_day_sonnet`) and
  extra-usage credits shown when the plan reports them.

## [1.0.0] - first release

### Added
- macOS menu-bar widget (SwiftBar/xbar plugin) showing Claude plan usage: the
  rolling 5-hour window and the weekly limit, for one or more accounts, using an
  existing Claude Code login (macOS Keychain or `~/.claude/.credentials.json`).

[1.2.0]: https://github.com/billjoel25/claude-usage-meter/releases/tag/v1.2.0
