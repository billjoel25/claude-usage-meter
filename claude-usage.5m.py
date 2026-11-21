#!/usr/bin/env python3
# <xbar.title>Claude Plan Usage</xbar.title>
# <xbar.version>1.2.0</xbar.version>
# <xbar.author>billjoel25</xbar.author>
# <xbar.author.github>billjoel25</xbar.author.github>
# <xbar.desc>Live Claude Pro/Max/Team plan usage in the menu bar - the current session and the weekly limit side by side, for one or more accounts. The dropdown adds reset times and per-model limits. Sign in with Claude (no CLI needed); shows the same server-truth numbers Claude enforces. Not API $ cost.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <xbar.abouturl>https://github.com/billjoel25/claude-usage-meter</xbar.abouturl>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
# (SwiftBar's own menu items are hidden; Option+Click the menu to show them.)
#
# Claude Plan Usage — a SwiftBar/xbar plugin. Pure Python 3, no pip installs.
# It shows how much of your Claude *plan* you've used, not dollars:
#   • menu bar = session · weekly, e.g. "2% · 30%" — the rolling 5-hour window,
#                then the 7-day cap (Anthropic's "seven_day"), always in that order
#   • pie      = before the numbers, fills clockwise as the 5-hour session runs; a
#                full disc means it's about to reset
#   • ring     = after the numbers, 7 day-segments fill as the week runs; a full
#                ring means the weekly limit is about to reset
#   • dropdown = both with their reset times, plus any per-model weekly caps and
#                extra-usage credits
# These are the exact percentages Claude shows in `/usage` and enforces on Pro/Max/Team.
#
# If your Claude org ever moves off Team (to Enterprise, say), you get one macOS
# notification. Nothing else about it shows. See "plan-change notice" below.
#
# Sign in from the menu ("Add Claude account") — no Claude Code CLI needed.
# Multiple accounts are supported; tokens are stored locally and auto-refreshed.
# An existing Claude Code login is also auto-detected. See README.md.
#
# Config (optional): ~/.config/claude-usage-meter/config.json — see load_config().

import json
import math
import os
import ssl
import struct
import subprocess
import sys
import time
import base64
import hashlib
import secrets
import zlib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
# The endpoint aggressively rate-limits requests without a claude-code User-Agent.
UA = "claude-code/2.0.0 (claude-usage-meter)"
CACHE_TTL = 180          # seconds — the endpoint 429s if polled harder than ~3 min
# How long the cache may stand in for a live reading. Long enough to carry a blip —
# a Keychain prompt that timed out, a dropped network, a 429 — and no longer. Past
# it the numbers clear themselves instead of waiting to be cleared by hand: a
# confidently wrong percentage in the menu bar is worse than no percentage.
STALE_MAX = 1800         # seconds (6 refresh ticks)
HTTP_TIMEOUT = 12        # seconds
APP_DIR = os.path.expanduser(os.environ.get("CLAUDE_USAGE_METER_HOME", "~/.config/claude-usage-meter"))
CACHE_DIR = os.path.join(APP_DIR, "cache")
ACCOUNTS_DIR = os.path.join(APP_DIR, "accounts")

# How usage is colored in the dropdown — "colors" in the config file:
#   'neutral' (default) — plain black text, every row, whatever the number. The
#                         percentage and its reset countdown say how close you are;
#                         color on top of that added worry, not information.
#   'status'            — green, then amber past AMBER_AT (and red past RED_AT, if set).
COLOR_MODES = ("neutral", "status")
COLOR_DEFAULT = "neutral"

# Utilization thresholds -> severity, used only in 'status' mode. Green until half,
# then amber, and that's as loud as it gets unless RED_AT is set (e.g. 85).
AMBER_AT = 50
RED_AT = None

# (light, dark) hex so it reads on both menu-bar appearances.
COLORS = {
    "green": ("#1a7f37", "#3fb950"),
    "amber": ("#9a6700", "#d4a72c"),
    "red":   ("#cf222e", "#ff7b72"),
    "dim":   ("#6e7781", "#8b949e"),
    # Plain text: black on a light menu, white on a dark one. Set explicitly because
    # SwiftBar draws an item with no action as disabled — leave the color off and a
    # usage row comes out gray, not black.
    "text":  ("#000000", "#ffffff"),
}
DOT = {"green": "🟢", "amber": "🟡", "red": "🔴", "dim": "⚪"}

# SF Symbols give a cleaner, native look than emoji. Single vivid tints that read
# on both light and dark menu bars; a gauge whose needle roughly matches the level.
SFCOLORS = {"green": "#34c759", "amber": "#ff9f0a", "red": "#ff453a", "dim": "#98989d"}
GAUGE = {"green": "gauge.low", "amber": "gauge.medium", "red": "gauge.high", "dim": "gauge"}


def sf(name):
    return SFCOLORS[name]


# The official Claude symbol (Claude_Symbol_1.png) as a base64 PNG template image,
# a 40px @2x (144 dpi) render so it stays crisp on Retina at ~20pt. SwiftBar tints
# it white on a dark menu bar / black on a light one.
CLAUDE_ICON = "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"


# ----------------------------------------------------------------------------- config

def default_config():
    """Sensible defaults so the widget works out of the box for one account and
    lights up a second one when its credentials become reachable."""
    return {
        "accounts": [
            # Personal: whatever `claude` is logged into (macOS Keychain, file fallback).
            {
                "label": "personal",
                "keychain_service": "Claude Code-credentials",
                "credentials_file": "~/.claude/.credentials.json",
            },
            # A second account: a Claude Code login under its own config dir.
            # Skipped silently until this file exists — see README (CLAUDE_CONFIG_DIR setup).
            {
                "label": "work",
                "credentials_file": "~/.claude-work/.credentials.json",
            },
        ]
    }


def config_candidates():
    cands = []
    env = os.environ.get("CLAUDE_USAGE_METER_CONFIG")
    if env:
        cands.append(os.path.expanduser(env))
    cands.append(os.path.join(APP_DIR, "config.json"))
    cands.append(os.path.expanduser("~/.clarity/claude-usage.json"))  # legacy Clarity build
    return cands


def config_path():
    for p in config_candidates():
        if os.path.exists(p):
            return p
    return os.path.join(APP_DIR, "config.json")


def load_config():
    for p in config_candidates():
        if os.path.exists(p):
            try:
                with open(p) as fh:
                    cfg = json.load(fh)
                if isinstance(cfg, dict) and isinstance(cfg.get("accounts"), list) and cfg["accounts"]:
                    return cfg
            except Exception:
                pass  # try the next candidate; the dropdown notes problems
    return default_config()


def _ensure_config():
    """Create a documented, empty starter config the first time, so there's a real
    file to edit by hand for the optional settings. Empty `accounts` keeps the onboarding + auto-detect
    paths intact — signed-in accounts and CLI logins are found without this file."""
    if any(os.path.exists(c) for c in config_candidates()):
        return
    p = os.path.join(APP_DIR, "config.json")
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(p, "w") as fh:
            json.dump({
                "_comment": "Optional — only for the advanced CLI/Keychain path. Accounts you "
                            "'Sign in with Claude' from the menu don't need this file. Move an "
                            "entry from _example into accounts to use it.",
                "accounts": [],
                "_example": [
                    {"label": "work",
                     "keychain_service": "Claude Code-credentials-XXXXXXXX",
                     "credentials_file": "~/.claude-work/.credentials.json"},
                ],
            }, fh, indent=2)
    except Exception:
        pass  # non-fatal; the widget still works without a config file


# --------------------------------------------------------------- display preferences
# Which accounts contribute their number to the menu bar, and in what order. Stored
# as `accounts_display` in the config file — an ordered list of
#   {"label": "personal", "menu_bar": true}
# (a bare "personal" string is accepted too, meaning "shown"). Accounts absent from
# the list keep their discovery order at the end and are shown, so the key is purely
# optional: without it nothing changes. Hiding an account only takes it out of the
# menu bar — its section, numbers and reset times stay in the dropdown.
DISPLAY_KEY = "accounts_display"


def _read_config():
    """The config file as a dict — {} when it's absent, unreadable, or not an object."""
    p = config_path()
    if os.path.exists(p):
        try:
            with open(p) as fh:
                cfg = json.load(fh)
            if isinstance(cfg, dict):
                return cfg
        except Exception:
            pass
    return {}


def _display_prefs():
    """[(label, show_in_menu_bar)] from the config, skipping malformed entries."""
    out = []
    for e in _read_config().get(DISPLAY_KEY) or []:
        if isinstance(e, str) and e:
            out.append((e, True))
        elif isinstance(e, dict) and e.get("label"):
            out.append((str(e["label"]), e.get("menu_bar", True) is not False))
    return out


def order_accounts(accounts, prefs=None):
    """`accounts` in display order: the ones named in `accounts_display` first, in
    that order, then anything it doesn't mention in discovery order. Labels in the
    config that no longer match an account are simply skipped."""
    prefs = _display_prefs() if prefs is None else prefs
    remaining = list(accounts)
    ordered = []
    for label, _ in prefs:
        for i, a in enumerate(remaining):
            if a.get("label") == label:
                ordered.append(remaining.pop(i))
                break
    return ordered + remaining


def hidden_labels(prefs=None):
    """Labels switched off for the menu bar. Anything unlisted is shown."""
    prefs = _display_prefs() if prefs is None else prefs
    return {label for label, show in prefs if not show}


def _config_for_write():
    """The config dict to modify, or None when the file exists but must not be
    touched (unreadable, or holding something other than an object)."""
    p = config_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as fh:
            cfg = json.load(fh)
    except Exception:
        return None
    return cfg if isinstance(cfg, dict) else None


def _write_display(entries):
    """Persist `entries` ([(label, show)]) as the display order, leaving every other
    key in the file alone. A config we can't safely rewrite is left untouched."""
    cfg = _config_for_write()
    if cfg is None:
        return
    cfg[DISPLAY_KEY] = [{"label": label, "menu_bar": show} for label, show in entries]
    p = config_path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(cfg, fh, indent=2)


def _current_entries():
    """Today's accounts as [(label, show)] in display order — the basis each menu
    action edits, so the first click writes a complete, hand-editable list and
    entries for accounts that are gone drop out."""
    prefs = _display_prefs()
    hidden = hidden_labels(prefs)
    return [(a.get("label", "account"), a.get("label") not in hidden)
            for a in order_accounts(load_accounts(), prefs)]


def do_toggle_account():
    """'toggle-account <label>' — show/hide that account's number in the menu bar."""
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    entries = _current_entries()
    if label not in [lbl for lbl, _ in entries]:
        raise SystemExit("usage: toggle-account <label>")
    _write_display([(lbl, (not show) if lbl == label else show) for lbl, show in entries])


def do_move_account():
    """'move-account <label> up|down' — reorder the accounts, menu bar and dropdown."""
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    direction = sys.argv[3] if len(sys.argv) > 3 else ""
    entries = _current_entries()
    labels = [lbl for lbl, _ in entries]
    if label not in labels or direction not in ("up", "down"):
        raise SystemExit("usage: move-account <label> [up|down]")
    i = labels.index(label)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(entries):          # already at the end: nothing to do
        entries[i], entries[j] = entries[j], entries[i]
        _write_display(entries)


# ------------------------------------------------------------ plan-change notice
# One job: a single macOS notification if your Claude org ever moves off Team.
# Enterprise is where org admins can gain access to your Claude Code session
# transcripts (through the Compliance API), so that move is worth hearing about.
# Nothing shows in the menu bar or the dropdown; you hear from this exactly when it
# happens, and never otherwise.
#
# The organizationType an Enterprise org reports isn't known, so this doesn't match
# a guessed string. It remembers the last value it read from ~/.claude.json and
# speaks up when "claude_team" turns into anything else, quoting what it now reads.
# A file it can't read is skipped — never reported as a change.

CLAUDE_JSON = "~/.claude.json"
TEAM = "claude_team"


def plan_state_path():
    return os.path.join(APP_DIR, "plan-state.json")


def _org_type():
    """oauthAccount.organizationType from ~/.claude.json, or None if unreadable."""
    try:
        with open(os.path.expanduser(CLAUDE_JSON)) as fh:
            acct = json.load(fh).get("oauthAccount")
        v = acct.get("organizationType") if isinstance(acct, dict) else None
        return v if isinstance(v, str) and v else None
    except Exception:
        return None


def _swiftbar_present():
    return bool(os.environ.get("SWIFTBAR")) or any(
        os.path.isdir(p) for p in ("/Applications/SwiftBar.app",
                                   os.path.expanduser("~/Applications/SwiftBar.app")))


def notify(title, body):
    """Post one macOS notification. Goes through SwiftBar's own notify scheme where
    SwiftBar is installed, so it arrives from SwiftBar; otherwise through osascript.
    Returns the app it was sent as ('SwiftBar' / 'Script Editor'), or None if no
    notifier ran. Sent is not the same as shown — `notify-test` checks that."""
    if sys.platform != "darwin":
        return None
    try:
        if _swiftbar_present():
            # SwiftBar addresses a plugin by its file name, e.g. claude-usage.5m.py
            plugin = os.path.basename(os.environ.get("SWIFTBAR_PLUGIN_PATH") or sys.argv[0])
            q = urllib.parse.urlencode({"plugin": plugin, "title": title, "body": body},
                                       quote_via=urllib.parse.quote)   # %20, never '+'
            cmd, via = ["/usr/bin/open", "-g", f"swiftbar://notify?{q}"], "SwiftBar"
        else:
            cmd = ["/usr/bin/osascript", "-e", "on run argv", "-e",
                   "display notification (item 2 of argv) with title (item 1 of argv)",
                   "-e", "end run", title, body]   # passed as argv: nothing to escape
            via = "Script Editor"
        subprocess.run(cmd, timeout=8, capture_output=True)
        return via
    except Exception:
        return None


def watch_plan():
    """Run once per tick. Notifies when organizationType moves off claude_team, and
    returns the message it sent — or None. Never raises."""
    seen = _org_type()
    if seen is None:
        return None                     # can't read it: say nothing, remember nothing
    try:
        with open(plan_state_path()) as fh:
            last = json.load(fh).get("organizationType")
    except Exception:
        last = None                     # first run, or a state file we can't use
    if seen == last:
        return None
    sent = None
    if last == TEAM:
        sent = (f"Your org is no longer on Team — it now reads “{seen}”. On Enterprise, "
                f"admins may be able to read your Claude Code sessions.")
        notify("Claude plan changed", sent)
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(plan_state_path(), "w") as fh:
            json.dump({"organizationType": seen}, fh)
    except Exception:
        pass
    return sent


# ------------------------------------------------------------------------ credentials

def _token_from_blob(blob):
    """Given the raw JSON string Claude Code stores, return (token, expires_at_ms)."""
    data = json.loads(blob)
    oauth = data.get("claudeAiOauth") or data.get("claude_ai_oauth") or data
    token = oauth.get("accessToken") or oauth.get("access_token")
    exp = oauth.get("expiresAt") or oauth.get("expires_at")
    return token, exp


def get_token(acct):
    """Resolve an account's bearer token from the first source that works.
    Returns (token, expires_at_ms, source_label) or (None, None, why-it-failed)."""
    if acct.get("access_token") and acct.get("refresh_token"):
        return _oauth_token(acct)
    # 1) Explicit shell command that prints a bare token (max flexibility).
    cmd = acct.get("token_cmd")
    if cmd:
        try:
            out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8)
            tok = out.stdout.strip()
            if tok:
                return tok, None, "token_cmd"
        except Exception:
            pass

    # 2) A literal token in the config (discouraged, but allowed).
    if acct.get("token"):
        return acct["token"], None, "config"

    # 3) A credentials file (Linux/WSL, or a second account under its own config dir).
    cf = acct.get("credentials_file")
    if cf:
        cf = os.path.expanduser(cf)
        if os.path.exists(cf):
            try:
                with open(cf) as fh:
                    tok, exp = _token_from_blob(fh.read())
                if tok:
                    return tok, exp, "file"
            except Exception:
                return None, None, "unreadable credentials file"

    # 4) macOS Keychain (the default Claude Code storage on a Mac).
    svc = acct.get("keychain_service")
    if svc and sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["security", "find-generic-password", "-s", svc, "-w"],
                capture_output=True, text=True, timeout=8,
            )
            if out.returncode == 0 and out.stdout.strip():
                tok, exp = _token_from_blob(out.stdout.strip())
                if tok:
                    return tok, exp, "keychain"
        except Exception:
            pass

    return None, None, "not logged in"


# ------------------------------------------------------------------------------ fetch

def fetch_usage(token):
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": UA,
            "Accept": "application/json",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cache_path(label):
    return os.path.join(CACHE_DIR, f"{_slug(label)}.json")


def _slug(s):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(s)).lower() or "acct"


def _store_usage(cp, data, now, source):
    """Cache a live reading and return it. A cache we can't write is not a reason to
    withhold numbers we just fetched."""
    try:
        with open(cp, "w") as fh:
            json.dump({"fetched_at": now, "data": data, "source": source}, fh)
    except Exception:
        pass
    return {"ok": True, "data": data, "stale": False, "age": 0, "error": None, "source": source}


def _retry_after_401(acct, cp, now, tried):
    """One self-healing retry after the server rejects a token: force a refresh and
    fetch again. An access token can be dead while the refresh token behind it still
    works, and recovering here saves a sign-out-and-re-add the user shouldn't need.

    Returns the live result, or None when there is no refresh token, the refresh
    didn't produce a different token, or the second attempt failed too."""
    if not acct.get("refresh_token"):
        return None
    try:
        token, _, source = _oauth_token(acct, force=True)
        if not token or token == tried:
            return None          # nothing new to try — don't spend a second request
        return _store_usage(cp, fetch_usage(token), now, source)
    except Exception:
        return None


def usage_for(acct):
    """Return dict: {ok, data, stale, age, error, source}. A 180s cache keeps us well
    under the endpoint's rate limit; beyond that the cache carries a transient failure
    for a while and then expires itself — see _fallback."""
    label = acct.get("label", "account")
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = cache_path(label)

    cached = None
    if os.path.exists(cp):
        try:
            with open(cp) as fh:
                cached = json.load(fh)
        except Exception:
            cached = None

    # Serve a fresh-enough cache without touching the network — unless a window it
    # describes has already reset, which makes it wrong however recently we fetched.
    now = time.time()
    if cached and (now - cached.get("fetched_at", 0)) < CACHE_TTL \
            and not _windows_reset(cached.get("data"), now):
        return {"ok": True, "data": cached["data"], "stale": False,
                "age": now - cached["fetched_at"], "error": None, "source": cached.get("source")}

    token, exp, source = get_token(acct)
    if not token:
        return _fallback(cached, now, error=source, cache_file=cp)

    # Signed-in (OAuth) accounts are refreshed in-app; a stale one means "re-add",
    # not "run claude" (which only applies to an auto-detected Claude Code login).
    is_oauth = acct.get("kind") == "oauth" or bool(acct.get("refresh_token"))

    if exp and _to_ms(exp) < now * 1000:
        return _fallback(cached, now, cache_file=cp, error=(
            "sign-in expired — sign out and re-add" if is_oauth
            else "token expired — run `claude` to refresh login"))

    try:
        return _store_usage(cp, fetch_usage(token), now, source)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            healed = _retry_after_401(acct, cp, now, token)
            if healed:
                return healed
            return _fallback(cached, now, cache_file=cp, drop=True, error=(
                "401 — sign-in invalid, re-add the account" if is_oauth
                else "401 — login invalid/expired, run `claude`"))
        if e.code == 429:
            return _fallback(cached, now, cache_file=cp, error="429 — rate limited, showing cache")
        return _fallback(cached, now, cache_file=cp, error=f"HTTP {e.code}")
    except Exception as e:
        return _fallback(cached, now, cache_file=cp, error=f"{type(e).__name__}")


def _iso_epoch(iso):
    """Epoch seconds for an ISO-8601 reset time, or None when it isn't one."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _windows_reset(data, now):
    """True once a window in this payload has passed its own resets_at. Whatever the
    number was, the window it described is over — so the number is wrong now, not
    merely old, however recently it was fetched."""
    if not isinstance(data, dict):
        return False
    for key in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
        when = _iso_epoch(util(data.get(key))[1])
        if when is not None and when <= now:
            return True
    return False


def _drop_cache(cache_file):
    """Delete a cache entry. Nothing in it is precious — it is a copy of a reading
    the server will hand back the moment we can ask again."""
    try:
        if cache_file and os.path.exists(cache_file):
            os.remove(cache_file)
    except Exception:
        pass          # non-fatal: worst case it expires again on the next tick


def _cache_expired(cached, now):
    """Can these cached numbers still be true? Unusable, past STALE_MAX, or
    describing a window that has since reset — all mean no."""
    if not isinstance(cached, dict) or "data" not in cached:
        return True
    if now - cached.get("fetched_at", 0) > STALE_MAX:
        return True
    return _windows_reset(cached.get("data"), now)


def _fallback(cached, now, error, cache_file=None, drop=False):
    """Stand in for a live reading with the last good numbers — but only while they
    can still be true. Once they can't, they are dropped *and deleted*, and the
    account reports the error on its own. `drop` forces that for a failure the
    numbers can't come back from by themselves.

    This is the clearing that used to need a trip to 'Force refresh (clear cache)'."""
    if drop or _cache_expired(cached, now):
        _drop_cache(cache_file)
        cached = None
    if cached and "data" in cached:
        return {"ok": True, "data": cached["data"], "stale": True,
                "age": now - cached.get("fetched_at", now), "error": error,
                "source": cached.get("source")}
    return {"ok": False, "data": None, "stale": False, "age": None, "error": error, "source": None}


def _to_ms(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    return v if v > 1e12 else v * 1000  # accept seconds or milliseconds


# --------------------------------------------------------------------------- rendering

def sev(pct):
    if pct is None:
        return "dim"
    if RED_AT is not None and pct >= RED_AT:
        return "red"
    if pct >= AMBER_AT:
        return "amber"
    return "green"


def color_mode():
    """'neutral' (default) or 'status' — `colors` in the config file."""
    v = _read_config().get("colors")
    return v if v in COLOR_MODES else COLOR_DEFAULT


def bar(pct, cells=10):
    if pct is None:
        return "─" * cells
    filled = max(0, min(cells, round(pct / 100 * cells)))
    return "█" * filled + "░" * (cells - filled)


def color_param(name):
    lo, hi = COLORS[name]
    return f"{lo},{hi}"


def fmt_pct(pct):
    return "—" if pct is None else f"{round(pct)}%"


def fmt_reset(iso):
    """Human 'resets in 2h13m' for near windows, or a short date for far ones."""
    if not iso:
        return ""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    delta = (t - datetime.now(timezone.utc)).total_seconds()
    if delta <= 0:
        return "resetting now"
    mins = int(delta // 60)
    if mins < 60:
        return f"resets in {mins}m"
    hrs, m = divmod(mins, 60)
    if hrs < 48:
        return f"resets in {hrs}h{m:02d}m"
    days, h = divmod(hrs, 24)
    return f"resets in {days}d{h}h"


def util(obj):
    """Pull a numeric utilization out of a {utilization, resets_at} object."""
    if not isinstance(obj, dict):
        return None, None
    u = obj.get("utilization")
    try:
        u = float(u)
    except (TypeError, ValueError):
        u = None
    return u, obj.get("resets_at")


def _title_pct(data):
    """Menu-bar text for one account: session, then weekly — "2% · 30%". Each number
    keeps its place, so the weekly can never be read as the session. The weekly is
    left off when the payload has none; None when there's no session number at all,
    since the weekly never stands in for it. Per-model caps stay in the dropdown."""
    data = data if isinstance(data, dict) else {}
    session = util(data.get("five_hour"))[0]
    if session is None:
        return None
    week = util(data.get("seven_day"))[0]
    return f"{round(session)}%" + ("" if week is None else f" · {round(week)}%")


# --------------------------------------------------------------------- session pie
# Before the numbers, a pie shows how far the session is through its 5-hour window.
# The shaded slice grows clockwise from 12, like a clock face; a full disc means it's
# about to reset, an empty one means a fresh session (or none running).
#
# SwiftBar gives a plugin one image per menu-bar item, always left of the text, so
# the pie is that image (with the Claude logo in front of it when MENU_LOGO is on).
# It's a template image: macOS tints it to the menu bar's text color, white on a
# dark bar and black on a light one. Drawn in plain Python — zlib and struct, no
# imaging library.

SESSION_SECONDS = 5 * 3600
MENU_LOGO = False  # the Claude logo before the pie — off for now; True brings it back
PIE_PX = 36        # 18pt across at @2x — the same visual size the logo had
PIE_RING = 4       # outline, 2pt
PIE_GAP = 4        # between the outline and the slice, 2pt
PIE_PAD = 8        # after the pie: with macOS's own spacing, ~7.5pt to the numbers
PIE_SPACE = 10     # logo -> pie, when the logo is on


def _png_decode_rgba(data):
    """(width, height, rows) for an 8-bit RGBA, non-interlaced PNG — the logo."""
    pos, w, h, idat = 8, 0, 0, b""
    while pos < len(data):
        length, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            if (depth, ctype) != (8, 6):
                raise ValueError("expected an 8-bit RGBA PNG")
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    raw, stride, rows = zlib.decompress(idat), w * 4, []
    prev, i = bytearray(stride), 0
    for _ in range(h):
        kind, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):               # undo the PNG row filter in place
            a = line[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            if kind == 1:
                line[x] = (line[x] + a) & 255
            elif kind == 2:
                line[x] = (line[x] + b) & 255
            elif kind == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, rows


def _png_encode_rgba(w, h, rows, dpi=144):
    """RGBA rows -> PNG bytes. 144 dpi makes macOS draw it at @2x, like the logo."""
    def chunk(tag, body):
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))
    ppm = round(dpi / 0.0254)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def _pie_alpha(size, elapsed, ring=PIE_RING, gap=PIE_GAP, ss=4):
    """size x size coverage (0..1): a full outline, and inside it a slice growing
    clockwise from 12 for `elapsed` (0..1) of the circle; None draws the outline
    alone. Each pixel is sampled ss x ss times so the edges come out smooth."""
    c = size / 2.0
    r_out = c - 0.5
    r_in = r_out - ring
    r_slice = r_in - gap
    e = 0.0 if elapsed is None else max(0.0, min(1.0, elapsed))
    end = e * 2 * math.pi
    out = []
    for y in range(size):
        row = []
        for x in range(size):
            hit = 0
            for sy in range(ss):
                dy = y + (sy + 0.5) / ss - c
                for sx in range(ss):
                    dx = x + (sx + 0.5) / ss - c
                    d = math.hypot(dx, dy)
                    if r_in <= d <= r_out:
                        hit += 1
                    elif d <= r_slice and e > 0 and \
                            (e >= 0.999 or math.atan2(dx, -dy) % (2 * math.pi) <= end):
                        hit += 1
            row.append(hit / (ss * ss))
        out.append(row)
    return out


def _session_elapsed(data, now=None):
    """How far the session is through its 5-hour window (0..1), or None when none is
    running — no reset time, or one that has already passed."""
    data = data if isinstance(data, dict) else {}
    when = _iso_epoch(util(data.get("five_hour"))[1])
    if when is None:
        return None
    left = when - (time.time() if now is None else now)
    if left <= 0:
        return None
    return max(0.0, min(1.0, 1 - left / SESSION_SECONDS))


def menu_icon(elapsed):
    """Base64 template PNG: the session pie with a little room after it for the
    numbers — and the Claude logo in front when MENU_LOGO is on."""
    lw = lh = 0
    if MENU_LOGO:
        lw, lh, logo = _png_decode_rgba(base64.b64decode(CLAUDE_ICON))
    x0 = lw + PIE_SPACE if MENU_LOGO else 0
    w, h = x0 + PIE_PX + PIE_PAD, max(lh, PIE_PX)
    canvas = [bytearray(w * 4) for _ in range(h)]
    if MENU_LOGO:
        top = (h - lh) // 2
        for y in range(lh):
            canvas[top + y][0:lw * 4] = logo[y]
    top = (h - PIE_PX) // 2
    for y, row in enumerate(_pie_alpha(PIE_PX, elapsed)):
        line = canvas[top + y]
        for x, cover in enumerate(row):
            o = (x0 + x) * 4
            line[o:o + 4] = bytes((0, 0, 0, int(round(cover * 255))))
    return base64.b64encode(_png_encode_rgba(w, h, canvas)).decode("ascii")


def _title_icon(data):
    """This account's session pie — or, if drawing it fails for any reason, the
    plain logo when MENU_LOGO is on and no image at all when it's off. Decoration
    never takes the menu bar down."""
    try:
        return menu_icon(_session_elapsed(data))
    except Exception:
        return CLAUDE_ICON if MENU_LOGO else None


def _image_param(b64):
    """'templateImage=<b64> ' for a menu-bar line, or '' with no image."""
    return f"templateImage={b64} " if b64 else ""


# ------------------------------------------------------- week ring + drawn numbers
# After the numbers, a ring of 7 day-segments shows how far the week is through
# its 7-day window, filling clockwise from 12 like the pie: bright days are gone,
# dim ones still to come, and a full ring means the weekly limit is about to reset.
#
# SwiftBar only ever draws an item's image BEFORE its text, so to get the ring
# after the numbers the whole title — pie, numbers, ring — is drawn as one image,
# with the numbers set from a small glyph atlas (below). Inter SemiBold at 22px
# measured within 1pt of macOS's own menu-bar numbers, at 98% of their stroke
# weight. The cost: drawn numbers are pixels, so a screen reader can't read them
# (SwiftBar sets no label on the menu-bar button). Several accounts, or WEEK_RING
# off, keep macOS's own text and the pie alone.
#
# The atlas glyphs are rendered from Inter (Copyright 2016-2023 The Inter Project
# Authors), so GLYPH_ATLAS is a derivative of the font and is licensed under the
# SIL Open Font License 1.1 — its text is at the end of this file, and in
# licenses/Inter-OFL.txt. Regenerate it with tools/make_glyph_atlas.py.
# Everything else in this file is MIT.

WEEK_SECONDS = 7 * 86400
WEEK_RING = True    # the 7-day ring after the numbers; False keeps macOS's own text
RING_PX = 30        # a tad smaller than the pie (36): the session leads, the week follows
RING_BAND = 4       # thickness of the day segments, 2pt, like the pie's outline
RING_DAY_GAP = 2.5  # between days, along the ring
RING_DIM = 0.32     # days still to come
TEXT_GAP = 15       # pie -> numbers and numbers -> ring, ink to ink (7.5pt)

# Generated by tools/make_glyph_atlas.py, from here to GLYPH_ATLAS.
GLYPH_H = 22        # cell height; baseline at row 18, caps from row 2
GLYPH_CAP_MID = 10  # vertical middle of the digits, within a cell
GLYPH_PAD = 2       # cells start this far left of the pen position
GLYPHS = {          # char: (x in atlas, cell width, advance), all px @2x
    '0': (0, 19, 14.516),
    '1': (19, 14, 9.297),
    '2': (33, 18, 13.703),
    '3': (51, 18, 14.0),
    '4': (69, 19, 14.656),
    '5': (88, 18, 13.844),
    '6': (106, 19, 14.078),
    '7': (125, 17, 12.672),
    '8': (142, 19, 14.078),
    '9': (161, 19, 14.078),
    '%': (180, 27, 22.094),
    '·': (207, 12, 7.016),
    ' ': (0, 0, 5.547),
}
GLYPH_ATLAS = "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"


def _week_elapsed(data, now=None):
    """How far the week is through its 7-day window (0..1), or None when there's
    no reset time to go by, or it has already passed."""
    data = data if isinstance(data, dict) else {}
    when = _iso_epoch(util(data.get("seven_day"))[1])
    if when is None:
        return None
    left = when - (time.time() if now is None else now)
    if left <= 0:
        return None
    return max(0.0, min(1.0, 1 - left / WEEK_SECONDS))


def _day_ring_alpha(size, elapsed, band=RING_BAND, day_gap=RING_DAY_GAP, ss=4):
    """size x size coverage (0..1): a ring cut into 7 day-segments starting at 12,
    bright for the part of the week gone, dim for the rest; None is all dim."""
    c = size / 2.0
    r_out = c - 0.5
    r_band = r_out - band
    r_mid = (r_out + r_band) / 2
    half_gap = day_gap / 2.0 / r_mid                 # radians either side of a day boundary
    day = 2 * math.pi / 7
    end = (0.0 if elapsed is None else max(0.0, min(1.0, elapsed))) * 2 * math.pi
    out = []
    for y in range(size):
        row = []
        for x in range(size):
            acc = 0.0
            for sy in range(ss):
                dy = y + (sy + 0.5) / ss - c
                for sx in range(ss):
                    dx = x + (sx + 0.5) / ss - c
                    if not r_band <= math.hypot(dx, dy) <= r_out:
                        continue
                    th = math.atan2(dx, -dy) % (2 * math.pi)
                    k = th / day
                    if abs(k - round(k)) * day <= half_gap:   # in a gap between days
                        continue
                    acc += 1.0 if th <= end else RING_DIM
            row.append(acc / (ss * ss))
        out.append(row)
    return out


_ATLAS = None


def _atlas():
    """The glyph atlas as (width, height, RGBA rows), decoded once per run."""
    global _ATLAS
    if _ATLAS is None:
        _ATLAS = _png_decode_rgba(base64.b64decode(GLYPH_ATLAS))
    return _ATLAS


def _text_alpha(text):
    """(width, rows) for `text` set from the glyph atlas, cropped to its ink; rows
    are GLYPH_H tall, 0..255. A character the atlas lacks advances like a space."""
    _, _, atlas = _atlas()
    total = sum(GLYPHS.get(ch, GLYPHS[" "])[2] for ch in text)
    width = int(math.ceil(total)) + 4 * GLYPH_PAD + 2
    rows = [[0] * width for _ in range(GLYPH_H)]
    pen = float(GLYPH_PAD)
    for ch in text:
        gx, gw, advance = GLYPHS.get(ch, GLYPHS[" "])
        x = int(round(pen)) - GLYPH_PAD
        for y in range(GLYPH_H):
            src, dst = atlas[y], rows[y]
            for i in range(gw):
                a = src[(gx + i) * 4 + 3]
                if a > dst[x + i]:
                    dst[x + i] = a
        pen += advance
    ink = [x for x in range(width) if any(rows[y][x] for y in range(GLYPH_H))]
    if not ink:
        return 0, [[] for _ in range(GLYPH_H)]
    return ink[-1] + 1 - ink[0], [r[ink[0]:ink[-1] + 1] for r in rows]


def _put(canvas, x0, top, rows, scale):
    """Draw coverage rows into the canvas's alpha channel (scale 255 for 0..1
    coverage, 1 for 0..255), keeping whichever is stronger where they meet."""
    for y, row in enumerate(rows):
        line = canvas[top + y]
        for x, v in enumerate(row):
            a = min(255, int(round(v * scale)))
            o = (x0 + x) * 4 + 3
            if a > line[o]:
                line[o] = a


def title_image(data, text):
    """Base64 template PNG for one account's whole title: [pie] numbers [week ring],
    the numbers drawn from the glyph atlas. The ring is left off when there's no
    weekly number to go with it."""
    lw = lh = 0
    if MENU_LOGO:
        lw, lh, logo = _png_decode_rgba(base64.b64decode(CLAUDE_ICON))
    tw, text_rows = _text_alpha(text)
    ring = isinstance(data, dict) and util(data.get("seven_day"))[0] is not None
    h = max(lh, PIE_PX, RING_PX if ring else 0)
    x_pie = lw + PIE_SPACE if MENU_LOGO else 0
    x_text = x_pie + PIE_PX + TEXT_GAP
    x_ring = x_text + tw + TEXT_GAP
    w = x_ring + RING_PX if ring else x_text + tw
    canvas = [bytearray(w * 4) for _ in range(h)]
    if MENU_LOGO:
        top = (h - lh) // 2
        for y in range(lh):
            canvas[top + y][0:lw * 4] = logo[y]
    _put(canvas, x_pie, (h - PIE_PX) // 2, _pie_alpha(PIE_PX, _session_elapsed(data)), 255)
    _put(canvas, x_text, h // 2 - GLYPH_CAP_MID, text_rows, 1)
    if ring:
        _put(canvas, x_ring, (h - RING_PX) // 2, _day_ring_alpha(RING_PX, _week_elapsed(data)), 255)
    return base64.b64encode(_png_encode_rgba(w, h, canvas)).decode("ascii")


def _drawn_title(data, text):
    """title_image(), or None if anything goes wrong — the caller then falls back
    to macOS's own text. Decoration never takes the menu bar down."""
    try:
        return title_image(data, text)
    except Exception:
        return None


def account_lines(acct, res, in_bar=True):
    """Yield SwiftBar dropdown lines for one account. Returns (lines, worst_pct).
    `in_bar` is False for an account switched off in the menu bar — it still gets its
    full section here, just a note saying why its numbers aren't up top."""
    label = acct.get("label", "account")
    lines = []
    worst = None

    if not res["ok"]:
        err = res["error"] or "not logged in"
        lines.append(f"{label} — {err} "
                     f"| sfimage=circle.dashed sfcolor={sf('dim')} color={color_param('dim')} "
                     f"font=Menlo-Bold size=13 trim=false")
        auth = any(k in err for k in ("401", "sign-in", "logged in", "token"))
        hint = ("Not logged into this account, or credentials unreachable — "
                "sign it in again with ➕ Add Claude account." if auth else
                "No live reading, and the cached numbers had expired — better nothing "
                "than something wrong.")
        lines.append(f"-- {hint} | color={color_param('dim')} size=12")
        return lines, worst

    data = res["data"] if isinstance(res["data"], dict) else {}
    five_u, five_r = util(data.get("five_hour"))
    week_u, week_r = util(data.get("seven_day"))
    # Per-model weekly caps (Max plans meter Opus/Sonnet separately) count toward this
    # account's status dot too — they're often the first limit you actually hit, and
    # leaving them out let the dot read "amber" while Opus was already maxed.
    model_u = [util(data.get(k))[0] for k in ("seven_day_opus", "seven_day_sonnet")]
    worst = max([p for p in (five_u, week_u, *model_u) if p is not None], default=None)

    head = label + ("" if in_bar else "  ·  hidden from menu bar") \
                 + ("  (cached)" if res["stale"] else "")
    neutral = color_mode() == "neutral"
    if neutral:
        lines.append(f"{head} | color={color_param('text')} font=Menlo-Bold size=13 trim=false")
    else:
        lines.append(f"{head} | sfimage=circle.fill sfcolor={sf(sev(worst))} "
                     f"font=Menlo-Bold size=13 trim=false")

    def row(name, pct, reset):
        c = color_param("text" if neutral else sev(pct))
        text = f"  {name:<7} [{bar(pct)}] {fmt_pct(pct):>4}"
        r = fmt_reset(reset)
        if r:
            text += f"   {r}"
        lines.append(f"{text} | font=Menlo size=13 trim=false color={c}")

    row("session", five_u, five_r)      # menu bar's first number: rolling 5-hour window
    row("weekly", week_u, week_r)       # …and its second: the 7-day cap

    # Per-model weekly limits (Max plans often meter Opus separately).
    for key, name in (("seven_day_opus", "· Opus"), ("seven_day_sonnet", "· Sonnet")):
        mu, mr = util(data.get(key))
        if mu is not None:
            row("  " + name, mu, mr)

    extra = data.get("extra_usage") or {}
    if extra.get("is_enabled"):
        used = extra.get("used_credits")
        limit = extra.get("monthly_limit")
        if used is not None and limit:
            lines.append(f"  extra usage: {used}/{limit} credits this month "
                         f"| font=Menlo size=12 trim=false color={color_param('dim')}")

    if res["error"]:
        lines.append(f"  ⚠︎ {res['error']} | size=12 trim=false "
                     f"color={color_param('text' if neutral else 'amber')}")

    if acct.get("kind") == "oauth" or acct.get("refresh_token"):
        lines.append(f'  ↳ sign out | bash=/bin/rm param1=-f param2="{account_file(label)}" '
                     f"terminal=false refresh=true color={color_param('dim')} size=11 trim=false")

    return lines, worst


# ------------------------------------------------------------------ sign in (OAuth)
# A friendly "Sign in with Claude" flow (Authorization Code + PKCE) so users don't
# need the Claude Code CLI or manual Keychain wiring. Uses Claude's public OAuth
# client; access + refresh tokens are stored per account under ACCOUNTS_DIR and
# refreshed automatically. Endpoints/scopes match Claude Code's subscription login.
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_AUTHORIZE = "https://claude.ai/oauth/authorize"
OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
OAUTH_REDIRECT = "https://platform.claude.com/oauth/code/callback"
OAUTH_SCOPE = "user:inference user:profile"  # profile is required by the usage endpoint


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _pkce():
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def _authorize_url(challenge, state):
    q = urllib.parse.urlencode({
        "code": "true",
        "client_id": OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": OAUTH_REDIRECT,
        "scope": OAUTH_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return f"{OAUTH_AUTHORIZE}?{q}"


def _oauth_post(payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(OAUTH_TOKEN_URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def account_file(label):
    return os.path.join(ACCOUNTS_DIR, f"{_slug(label)}.json")


def _store_tokens(label, tok, email=None):
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    exp = tok.get("expires_in")
    data = {
        "label": label,
        "kind": "oauth",
        "access_token": tok.get("access_token"),
        "refresh_token": tok.get("refresh_token"),
        "expires_at": int(time.time() * 1000) + int(exp) * 1000 if exp else None,
        "email": email or (tok.get("account") or {}).get("email_address"),
        "client_id": OAUTH_CLIENT_ID,
    }
    p = account_file(label)
    with open(p, "w") as fh:
        json.dump(data, fh, indent=2)
    os.chmod(p, 0o600)
    return data


def _oauth_token(acct, force=False):
    """(access_token, expires_at_ms, source) for an app-managed account, refreshing
    via the refresh_token when the access token is stale — or when `force` says the
    server has already rejected it, whatever the stored expiry claims."""
    now_ms = int(time.time() * 1000)
    exp = acct.get("expires_at")
    if not force and exp and exp - now_ms > 60_000:
        return acct.get("access_token"), exp, "signed in"
    rt = acct.get("refresh_token")
    if not rt:
        return acct.get("access_token"), exp, "signed in"
    try:
        new = _oauth_post({"grant_type": "refresh_token",
                           "refresh_token": rt, "client_id": OAUTH_CLIENT_ID})
        if not new.get("refresh_token"):
            new["refresh_token"] = rt
        data = _store_tokens(acct.get("label", "account"), new, email=acct.get("email"))
        return data["access_token"], data["expires_at"], "signed in"
    except Exception:
        if acct.get("access_token"):
            return acct.get("access_token"), exp, "signed in"
        return None, None, "sign-in expired — re-add the account"


def _app_accounts():
    out = []
    if os.path.isdir(ACCOUNTS_DIR):
        for fn in sorted(os.listdir(ACCOUNTS_DIR)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(ACCOUNTS_DIR, fn)) as fh:
                        a = json.load(fh)
                    if a.get("access_token"):
                        a.setdefault("label", fn[:-5])
                        a["kind"] = "oauth"
                        out.append(a)
                except Exception:
                    pass
    return out


def _manual_accounts():
    for p in config_candidates():
        if os.path.exists(p):
            try:
                with open(p) as fh:
                    cfg = json.load(fh)
                if isinstance(cfg, dict) and isinstance(cfg.get("accounts"), list):
                    return cfg["accounts"]
            except Exception:
                pass
    return []


def load_accounts():
    app = _app_accounts()
    seen = {a.get("label") for a in app}
    manual = [a for a in _manual_accounts() if a.get("label") not in seen]
    return (app + manual) or default_config()["accounts"]


def _existing_account_email(label):
    """Email stored in the account file for `label`: '' if none stored / unreadable,
    or None if there is no such file yet."""
    p = account_file(label)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as fh:
            return json.load(fh).get("email") or ""
    except Exception:
        return ""


def _unique_label(label, email):
    """Keep a sign-in from silently clobbering a *different* account that slugs to the
    same filename (e.g. alice@gmail.com and alice@work.com both default to 'alice', or
    two email-less logins both default to 'claude'). Re-authenticating the same email
    keeps its label; a genuine collision gets a numeric suffix."""
    existing = _existing_account_email(label)
    if existing is None:
        return label                      # no file yet — free to use
    if email and existing == email:
        return label                      # same account refreshing in place
    n = 2
    while True:
        cand = f"{label}-{n}"
        ex = _existing_account_email(cand)
        if ex is None or (email and ex == email):
            return cand
        n += 1


def do_signin():
    """Interactive 'Sign in with Claude' — launched in a Terminal from the menu."""
    label_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    print("\n  Sign in to Claude — add an account to your usage meter")
    print("  " + "-" * 53)
    verifier, challenge = _pkce()
    state = _b64url(secrets.token_bytes(32))
    url = _authorize_url(challenge, state)
    print("\n  1) A browser window will open. Sign in and approve access.")
    print("     (If it doesn't open, paste this URL into your browser:)\n")
    print("     " + url + "\n")
    try:
        subprocess.run(["open", url], check=False)
    except Exception:
        pass
    print("  2) Claude then shows you a code that looks like  ABC123#XYZ")
    try:
        raw = input("\n  3) Paste the whole code here and press Enter:\n     > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Aborted.\n")
        return
    if not raw:
        print("\n  ✗ No code entered. Nothing changed.\n")
        return
    code = raw.split("#", 1)[0].strip()
    ret_state = raw.split("#", 1)[1].strip() if "#" in raw else ""
    if ret_state and ret_state != state:
        print("\n  ⚠︎ Security check failed (state mismatch). Please try again.\n")
        return
    print("\n  Signing you in…")
    try:
        tok = _oauth_post({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": OAUTH_REDIRECT,
            "client_id": OAUTH_CLIENT_ID,
            "code_verifier": verifier,
            "state": state,
        })
    except Exception as e:
        detail = ""
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail = " — " + e.read().decode("utf-8")[:200]
            except Exception:
                detail = f" — HTTP {e.code}"
        print(f"\n  ✗ Sign-in failed{detail}\n")
        return
    email = (tok.get("account") or {}).get("email_address") or ""
    default_label = label_arg or (email.split("@")[0] if email else "claude") or "claude"
    try:
        label = input(f"\n  Name this account [{default_label}]: ").strip() or default_label
    except (EOFError, KeyboardInterrupt):
        label = default_label
    safe = _unique_label(label, email)
    if safe != label:
        print(f"\n  ⚠︎ An account named “{label}” already exists — saving this one as “{safe}”")
        print("     so it won't overwrite the other. Rename it later from the config file.")
        label = safe
    _store_tokens(label, tok, email=email)
    _drop_cache(cache_path(label))   # a re-add starts clean, not on the old numbers
    who = email or label
    print(f"\n  ✓ Signed in as {who}.")
    print("    It appears in the menu bar within a few minutes — or click the")
    print("    Claude icon → Refresh now.\n")


def _accounts_menu(plugin, accounts, prefs):
    """The 'Accounts' submenu: click an account to show/hide its number in the menu
    bar, and move it to reorder both the menu bar and the sections above."""
    if not accounts:
        return
    hidden = hidden_labels(prefs)
    dim = color_param("dim")
    print("Accounts")
    print(f"-- Click an account to show or hide it in the menu bar. | color={dim} size=11 trim=false")
    for i, acct in enumerate(accounts):
        label = acct.get("label", "account")
        on = label not in hidden
        print(f'-- {"✓" if on else "☐"} {label} | bash="{plugin}" param1=toggle-account '
              f'param2="{label}" terminal=false refresh=true trim=false size=13'
              f"{'' if on else f' color={dim}'}")
        for name, direction, ok in (("↑ move up", "up", i > 0),
                                    ("↓ move down", "down", i < len(accounts) - 1)):
            if ok:
                print(f'--     {name} | bash="{plugin}" param1=move-account param2="{label}" '
                      f"param3={direction} terminal=false refresh=true trim=false "
                      f"color={dim} size=11")


def _footer(accounts=(), prefs=()):
    # ---- actions ----
    plugin = os.path.realpath(sys.argv[0])
    print(f'➕ Add Claude account… | bash="{plugin}" param1=signin terminal=true')
    print("Refresh now | refresh=true")
    print("Force refresh (clear cache) | bash=/bin/rm param1=-rf "
          f'param2="{CACHE_DIR}" terminal=false refresh=true')
    _accounts_menu(plugin, accounts, prefs)


def _welcome():
    print(f"Claude | {_image_param(CLAUDE_ICON if MENU_LOGO else None)}size=11 "
          f"color={color_param('dim')}")
    print("---")
    print(f"Claude plan usage | size=12 color={color_param('dim')}")
    print("---")
    print("Not signed in yet | font=Menlo-Bold size=13 trim=false")
    print(f"Add your Claude account below to see your current session usage. "
          f"| color={color_param('dim')} size=12 trim=false")
    print("---")
    _footer()


def main():
    _ensure_config()
    try:
        watch_plan()                # silent unless the org moves off Team
    except Exception:
        pass                        # never let the watcher take the widget down
    prefs = _display_prefs()
    hidden = hidden_labels(prefs)
    accounts = order_accounts(load_accounts(), prefs)
    rendered = []           # (acct, res, lines, worst) — computed once per account
    for acct in accounts:
        res = usage_for(acct)
        lines, worst = account_lines(acct, res, acct.get("label") not in hidden)
        rendered.append((acct, res, lines, worst))

    # Onboard only when there's genuinely nothing to show: no signed-in account, no
    # hand-written config, and no auto-detected Claude Code login returning data. This
    # keeps the friendly welcome for fresh installs while still auto-detecting a CLI login.
    have_data = any(res["ok"] and res["data"] for _, res, _, _ in rendered)
    explicit = bool(_app_accounts()) or bool(_manual_accounts())
    if not have_data and not explicit:
        _welcome()
        return

    # ---- menu bar title: session · weekly, in the user's order, for each account
    # ---- switched on that reports a session. Per-model limits — and the accounts
    # ---- switched off — stay in the dropdown ----
    shown = []          # (initial, text like "42% · 30%")
    pie_data = None     # the first shown account's payload drives the session pie
    for acct, res, _, _ in rendered:
        if acct.get("label") in hidden:
            continue
        text = _title_pct(res["data"]) if res["ok"] else None
        if text is not None:
            label = acct.get("label", "?")
            shown.append((label[0].upper() if label else "?", text))
            if pie_data is None:
                pie_data = res["data"]

    if not shown:
        # configured, but nothing readable yet — stay quiet and subtle
        print(f"Claude | {_image_param(CLAUDE_ICON if MENU_LOGO else None)}size=11 "
              f"color={color_param('dim')}")
    else:
        # " · " sits inside an account (session · weekly), so accounts are set apart
        # by their initials and a wider gap: "W 2% · 30%   P 5% · 10%"
        text = shown[0][1] if len(shown) == 1 else "   ".join(f"{i} {p}" for i, p in shown)
        drawn = _drawn_title(pie_data, text) if WEEK_RING and len(shown) == 1 else None
        if drawn:
            # pie, numbers and week ring as one image — SwiftBar puts images before text,
            # so this is the only way the ring can sit after the numbers
            print(f"| templateImage={drawn}")
        else:
            # session pie (one template image) + numbers in macOS's own text
            print(f"{text} | {_image_param(_title_icon(pie_data))}size=11")

    print("---")
    print(f"Claude plan usage  ·  updated {datetime.now().strftime('%H:%M')} "
          f"| size=12 color={color_param('dim')}")
    print("---")

    for acct, res, lines, worst in rendered:
        for ln in lines:
            print(ln)
        print("---")

    _footer(accounts, prefs)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "signin":
        do_signin()
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "notify-test":
        via = notify("Claude plan changed (test)",
                     "This is how you'll hear if your org ever moves off Team.")
        print(f"Sent as {via}. If nothing appeared, allow notifications for {via} in "
              f"System Settings → Notifications." if via else "Notifications need macOS.")
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "toggle-account":
        do_toggle_account()
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "move-account":
        do_move_account()
        raise SystemExit(0)
    try:
        main()
    except Exception:
        import traceback
        print("⚠︎ Claude usage | color=#cf222e,#ff7b72")
        print("---")
        print("The widget hit an error:")
        for line in traceback.format_exc().splitlines():
            print(f"{line} | font=Menlo size=11 trim=false")


# ------------------------------------------------------------- GLYPH_ATLAS license
# A copy of this file installed on its own carries the glyph atlas's license with
# it. Kept identical to licenses/Inter-OFL.txt (the tests check).
#
# >>> licenses/Inter-OFL.txt
# The digits, "%" and "·" that claude-usage.5m.py draws in the menu bar (its
# GLYPH_ATLAS) are rendered from the Inter typeface, SemiBold. That glyph atlas
# is licensed under the SIL Open Font License 1.1, below. Everything else in this
# project is under the MIT License (see LICENSE).
#
# Copyright 2016-2023 The Inter Project Authors (https://github.com/rsms/inter)
#
# This Font Software is licensed under the SIL Open Font License, Version 1.1.
# This license is copied below, and is also available with a FAQ at:
# https://openfontlicense.org
#
# -----------------------------------------------------------
#
# SIL OPEN FONT LICENSE
#
# Version 1.1 - 26 February 2007
#
# PREAMBLE
#
# The goals of the Open Font License (OFL) are to stimulate worldwide development of collaborative font projects, to support the font creation efforts of academic and linguistic communities, and to provide a free and open framework in which fonts may be shared and improved in partnership with others.
#
# The OFL allows the licensed fonts to be used, studied, modified and redistributed freely as long as they are not sold by themselves. The fonts, including any derivative works, can be bundled, embedded, redistributed and/or sold with any software provided that any reserved names are not used by derivative works. The fonts and derivatives, however, cannot be released under any other type of license. The requirement for fonts to remain under this license does not apply to any document created using the fonts or their derivatives.
#
# DEFINITIONS
#
# "Font Software" refers to the set of files released by the Copyright Holder(s) under this license and clearly marked as such. This may include source files, build scripts and documentation.
#
# "Reserved Font Name" refers to any names specified as such after the copyright statement(s).
#
# "Original Version" refers to the collection of Font Software components as distributed by the Copyright Holder(s).
#
# "Modified Version" refers to any derivative made by adding to, deleting, or substituting — in part or in whole — any of the components of the Original Version, by changing formats or by porting the Font Software to a new environment.
#
# "Author" refers to any designer, engineer, programmer, technical writer or other person who contributed to the Font Software.
#
# PERMISSION & CONDITIONS
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of the Font Software, to use, study, copy, merge, embed, modify, redistribute, and sell modified and unmodified copies of the Font Software, subject to the following conditions:
#
# 1) Neither the Font Software nor any of its individual components, in Original or Modified Versions, may be sold by itself.
#
# 2) Original or Modified Versions of the Font Software may be bundled, redistributed and/or sold with any software, provided that each copy contains the above copyright notice and this license. These can be included either as stand-alone text files, human-readable headers or in the appropriate machine-readable metadata fields within text or binary files as long as those fields can be easily viewed by the user.
#
# 3) No Modified Version of the Font Software may use the Reserved Font Name(s) unless explicit written permission is granted by the corresponding Copyright Holder. This restriction only applies to the primary font name as presented to the users.
#
# 4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font Software shall not be used to promote, endorse or advertise any Modified Version, except to acknowledge the contribution(s) of the Copyright Holder(s) and the Author(s) or with their explicit written permission.
#
# 5) The Font Software, modified or unmodified, in part or in whole, must be distributed entirely under this license, and must not be distributed under any other license. The requirement for fonts to remain under this license does not apply to any document created using the Font Software.
#
# TERMINATION
#
# This license becomes null and void if any of the above conditions are not met.
#
# DISCLAIMER
#
# THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM OTHER DEALINGS IN THE FONT SOFTWARE.
