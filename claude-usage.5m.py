#!/usr/bin/env python3
# <xbar.title>Claude Plan Usage</xbar.title>
# <xbar.version>1.2.0</xbar.version>
# <xbar.author>billjoel25</xbar.author>
# <xbar.author.github>billjoel25</xbar.author.github>
# <xbar.desc>Live Claude Pro/Max/Team plan usage in the menu bar - the rolling 5-hour window and the weekly limit, for one or more accounts. Sign in with Claude (no CLI needed); shows the same server-truth numbers Claude enforces. Not API $ cost.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <xbar.abouturl>https://github.com/billjoel25/claude-usage-meter</xbar.abouturl>
# <swiftbar.hideAbout>false</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>false</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>false</swiftbar.hideDisablePlugin>
#
# Claude Plan Usage — a SwiftBar/xbar plugin. Pure Python 3, no pip installs.
# It shows how much of your Claude *plan* you've used, not dollars:
#   • 5-hour  = the rolling burst window
#   • weekly  = the 7-day cap (Anthropic's "seven_day")
# These are the exact percentages Claude shows in `/usage` and enforces on Pro/Max/Team.
#
# Sign in from the menu ("Add Claude account") — no Claude Code CLI needed.
# Multiple accounts are supported; tokens are stored locally and auto-refreshed.
# An existing Claude Code login is also auto-detected. See README.md.
#
# Config (optional): ~/.config/claude-usage-meter/config.json — see load_config().

import json
import os
import ssl
import subprocess
import sys
import time
import base64
import hashlib
import secrets
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
# The endpoint aggressively rate-limits requests without a claude-code User-Agent.
UA = "claude-code/2.0.0 (claude-usage-meter)"
CACHE_TTL = 180          # seconds — the endpoint 429s if polled harder than ~3 min
HTTP_TIMEOUT = 12        # seconds
APP_DIR = os.path.expanduser(os.environ.get("CLAUDE_USAGE_METER_HOME", "~/.config/claude-usage-meter"))
CACHE_DIR = os.path.join(APP_DIR, "cache")
ACCOUNTS_DIR = os.path.join(APP_DIR, "accounts")

# Utilization thresholds -> severity. Green until half, amber, red near the ceiling.
AMBER_AT = 50
RED_AT = 85

# (light, dark) hex so it reads on both menu-bar appearances.
COLORS = {
    "green": ("#1a7f37", "#3fb950"),
    "amber": ("#9a6700", "#d4a72c"),
    "red":   ("#cf222e", "#ff7b72"),
    "dim":   ("#6e7781", "#8b949e"),
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
    """Create a documented, empty starter config the first time so 'Edit config file'
    always opens something real. Empty `accounts` keeps the onboarding + auto-detect
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
                "menu_bar": "five_hour",
                "accounts": [],
                "_example": [
                    {"label": "work",
                     "keychain_service": "Claude Code-credentials-XXXXXXXX",
                     "credentials_file": "~/.claude-work/.credentials.json"},
                ],
            }, fh, indent=2)
    except Exception:
        pass  # non-fatal; the widget still works without a config file


# Which window the menu-bar number shows. 'auto' = the worst of all windows
# (including per-model caps); the dropdown always lists every window regardless.
DISPLAY_MODES = ("five_hour", "weekly", "both", "auto")
DISPLAY_DEFAULT = "five_hour"


def display_mode():
    """The user's menu-bar window choice — `menu_bar` in the config file."""
    p = config_path()
    if os.path.exists(p):
        try:
            with open(p) as fh:
                v = json.load(fh).get("menu_bar")
            if v in DISPLAY_MODES:
                return v
        except Exception:
            pass
    return DISPLAY_DEFAULT


def do_set_display():
    """Handle 'set-display <mode>' from the dropdown: persist the choice in the config."""
    value = sys.argv[2] if len(sys.argv) > 2 else ""
    if value not in DISPLAY_MODES:
        raise SystemExit(f"usage: set-display [{'|'.join(DISPLAY_MODES)}]")
    p = config_path()
    cfg = {}
    if os.path.exists(p):
        try:
            with open(p) as fh:
                loaded = json.load(fh)
            if not isinstance(loaded, dict):
                return  # unexpected shape — don't clobber it for a display tweak
            cfg = loaded
        except Exception:
            return      # unreadable — likewise leave the file alone
    cfg["menu_bar"] = value
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(cfg, fh, indent=2)


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


def usage_for(acct):
    """Return dict: {ok, data, stale, age, error, source}. Uses a 180s cache to
    stay well under the endpoint's rate limit and to survive transient failures."""
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

    # Serve a fresh-enough cache without touching the network.
    now = time.time()
    if cached and (now - cached.get("fetched_at", 0)) < CACHE_TTL:
        return {"ok": True, "data": cached["data"], "stale": False,
                "age": now - cached["fetched_at"], "error": None, "source": cached.get("source")}

    token, exp, source = get_token(acct)
    if not token:
        return _fallback(cached, now, error=source)

    # Signed-in (OAuth) accounts are refreshed in-app; a stale one means "re-add",
    # not "run claude" (which only applies to an auto-detected Claude Code login).
    is_oauth = acct.get("kind") == "oauth" or bool(acct.get("refresh_token"))

    if exp and _to_ms(exp) < now * 1000:
        return _fallback(cached, now, error=(
            "sign-in expired — sign out and re-add" if is_oauth
            else "token expired — run `claude` to refresh login"))

    try:
        data = fetch_usage(token)
        with open(cp, "w") as fh:
            json.dump({"fetched_at": now, "data": data, "source": source}, fh)
        return {"ok": True, "data": data, "stale": False, "age": 0, "error": None, "source": source}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return _fallback(cached, now, error=(
                "401 — sign-in invalid, re-add the account" if is_oauth
                else "401 — login invalid/expired, run `claude`"))
        if e.code == 429:
            return _fallback(cached, now, error="429 — rate limited, showing cache")
        return _fallback(cached, now, error=f"HTTP {e.code}")
    except Exception as e:
        return _fallback(cached, now, error=f"{type(e).__name__}")


def _fallback(cached, now, error):
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
    if pct >= RED_AT:
        return "red"
    if pct >= AMBER_AT:
        return "amber"
    return "green"


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


def _title_pct(data, worst, mode):
    """Menu-bar text for one account under the chosen display mode. Falls back to the
    worst window when the chosen one has no data; a ⚠ flags a window the user isn't
    showing (weekly, Opus, …) that is already in the red."""
    data = data if isinstance(data, dict) else {}
    five = util(data.get("five_hour"))[0]
    week = util(data.get("seven_day"))[0]
    if mode == "five_hour" and five is not None:
        text, visible = f"{round(five)}%", five
    elif mode == "weekly" and week is not None:
        text, visible = f"{round(week)}%", week
    elif mode == "both" and (five is not None or week is not None):
        f_txt = "–" if five is None else str(round(five))
        w_txt = "–" if week is None else str(round(week))
        text, visible = f"{f_txt}/{w_txt}%", max(v for v in (five, week) if v is not None)
    else:
        text, visible = f"{round(worst)}%", worst   # 'auto', or fallback
    if worst >= RED_AT and visible < RED_AT:
        text += "⚠"
    return text


def account_lines(acct, res):
    """Yield SwiftBar dropdown lines for one account. Returns (lines, worst_pct)."""
    label = acct.get("label", "account")
    lines = []
    worst = None

    if not res["ok"]:
        lines.append(f"{label} — {res['error'] or 'not logged in'} "
                     f"| sfimage=circle.dashed sfcolor={sf('dim')} color={color_param('dim')} "
                     f"font=Menlo-Bold size=13 trim=false")
        lines.append(f"-- Not logged into this account, or credentials unreachable. "
                     f"See 'About / setup'. | color={color_param('dim')} size=12")
        return lines, worst

    data = res["data"] if isinstance(res["data"], dict) else {}
    five_u, five_r = util(data.get("five_hour"))
    week_u, week_r = util(data.get("seven_day"))
    # Per-model weekly caps (Max plans meter Opus/Sonnet separately) count toward the
    # summary too — they're often the first limit you actually hit. Leaving them out
    # let the menu bar read "amber" while Opus was already maxed.
    model_u = [util(data.get(k))[0] for k in ("seven_day_opus", "seven_day_sonnet")]
    worst = max([p for p in (five_u, week_u, *model_u) if p is not None], default=None)

    head = label + ("  (cached)" if res["stale"] else "")
    lines.append(f"{head} | sfimage=circle.fill sfcolor={sf(sev(worst))} "
                 f"font=Menlo-Bold size=13 trim=false")

    def row(name, pct, reset):
        c = color_param(sev(pct))
        text = f"  {name:<7} [{bar(pct)}] {fmt_pct(pct):>4}"
        r = fmt_reset(reset)
        if r:
            text += f"   {r}"
        lines.append(f"{text} | font=Menlo size=13 trim=false color={c}")

    row("5-hour", five_u, five_r)
    row("weekly", week_u, week_r)

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
        lines.append(f"  ⚠︎ {res['error']} | size=12 color={color_param('amber')} trim=false")

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


def _oauth_token(acct):
    """(access_token, expires_at_ms, source) for an app-managed account, refreshing
    via the refresh_token when the access token is stale."""
    now_ms = int(time.time() * 1000)
    exp = acct.get("expires_at")
    if exp and exp - now_ms > 60_000:
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
    who = email or label
    print(f"\n  ✓ Signed in as {who}.")
    print("    It appears in the menu bar within a few minutes — or click the")
    print("    Claude icon → Refresh now.\n")


def _footer():
    # ---- actions ----
    plugin = os.path.realpath(sys.argv[0])
    print(f'➕ Add Claude account… | bash="{plugin}" param1=signin terminal=true')
    print("Refresh now | refresh=true")
    print("Force refresh (clear cache) | bash=/bin/rm param1=-rf "
          f'param2="{CACHE_DIR}" terminal=false refresh=true')
    mode = display_mode()
    print("Menu bar shows")
    for key, name in (("five_hour", "5-hour window"), ("weekly", "weekly window"),
                      ("both", "5-hour / weekly"), ("auto", "worst window")):
        mark = "✓ " if key == mode else "   "
        print(f'-- {mark}{name} | bash="{plugin}" param1=set-display param2={key} '
              f"terminal=false refresh=true trim=false")
    print("About / setup")
    print("-- Shows your Claude *plan* usage — the same 5-hour and weekly")
    print("-- percentages `/usage` shows, not API dollar cost.")
    print("-- Sign in via the menu, or an existing Claude Code login is auto-detected.")
    print("-- Source: Anthropic’s plan-usage endpoint (api.anthropic.com/api/oauth/usage).")
    print("-- Numbers are cached ~3 min to respect the rate limit.")
    print(f"-- Config: {config_path()}")
    print("-- | size=12")
    print(f'-- Edit config file | bash=/usr/bin/open param1=-t param2="{config_path()}" terminal=false')
    print("-- Project on GitHub | href=https://github.com/billjoel25/claude-usage-meter")


def _welcome():
    print(f"Claude | templateImage={CLAUDE_ICON} size=11 color={color_param('dim')}")
    print("---")
    print(f"Claude plan usage | size=12 color={color_param('dim')}")
    print("---")
    print("Not signed in yet | font=Menlo-Bold size=13 trim=false")
    print(f"Add your Claude account below to see your 5-hour & weekly limits. "
          f"| color={color_param('dim')} size=12 trim=false")
    print("---")
    _footer()


def main():
    _ensure_config()
    accounts = load_accounts()
    rendered = []           # (acct, res, lines, worst) — computed once per account
    for acct in accounts:
        res = usage_for(acct)
        lines, worst = account_lines(acct, res)
        rendered.append((acct, res, lines, worst))

    # Onboard only when there's genuinely nothing to show: no signed-in account, no
    # hand-written config, and no auto-detected Claude Code login returning data. This
    # keeps the friendly welcome for fresh installs while still auto-detecting a CLI login.
    have_data = any(res["ok"] and res["data"] for _, res, _, _ in rendered)
    explicit = bool(_app_accounts()) or bool(_manual_accounts())
    if not have_data and not explicit:
        _welcome()
        return

    # ---- menu bar title: only accounts that returned real numbers, showing the
    # ---- window the user picked under "Menu bar shows" (default: 5-hour) ----
    mode = display_mode()
    shown = []          # (initial, text like "42%" or "42/90%⚠")
    for acct, res, _, worst in rendered:
        if res["ok"] and worst is not None:
            label = acct.get("label", "?")
            shown.append((label[0].upper() if label else "?",
                          _title_pct(res["data"], worst, mode)))

    if not shown:
        # configured, but nothing readable yet — stay quiet and subtle
        print(f"Claude | templateImage={CLAUDE_ICON} size=11 color={color_param('dim')}")
    else:
        text = shown[0][1] if len(shown) == 1 else " · ".join(f"{i} {p}" for i, p in shown)
        # white Claude logo (template image) + white numbers (native color), 20% smaller
        print(f"{text} | templateImage={CLAUDE_ICON} size=11")

    print("---")
    print(f"Claude plan usage  ·  updated {datetime.now().strftime('%H:%M')} "
          f"| size=12 color={color_param('dim')}")
    print("---")

    for acct, res, lines, worst in rendered:
        for ln in lines:
            print(ln)
        print("---")

    _footer()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "signin":
        do_signin()
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "set-display":
        do_set_display()
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
