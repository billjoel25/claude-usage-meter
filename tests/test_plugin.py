#!/usr/bin/env python3
"""Dependency-free tests for claude-usage.5m.py.

Run:  python3 tests/test_plugin.py
No pip installs — plain asserts and a tiny runner, matching the plugin's ethos.
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, "..", "claude-usage.5m.py")


def load():
    spec = importlib.util.spec_from_file_location("claude_usage", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load()


def _isolate(tmp):
    """Point the module's filesystem paths at a throwaway dir."""
    m.APP_DIR = tmp
    m.CACHE_DIR = os.path.join(tmp, "cache")
    m.ACCOUNTS_DIR = os.path.join(tmp, "accounts")
    m.config_candidates = lambda: [os.path.join(tmp, "config.json")]
    m.config_path = lambda: os.path.join(tmp, "config.json")


def _title_of(out):
    """The menu-bar text of a rendered dropdown — the first line, minus its
    ` | key=value` params (which carry the base64 icon)."""
    return out.splitlines()[0].split(" | ", 1)[0]


def _render_main(data, label="personal"):
    """Run main() against a canned payload and return its stdout, with the account
    lookup and the network stubbed out."""
    saved = (m.load_accounts, m.usage_for)
    m.load_accounts = lambda: [{"label": label}]
    m.usage_for = lambda acct: {"ok": True, "data": data, "stale": False,
                                "age": 0, "error": None, "source": "stub"}
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            m.main()
    finally:
        m.load_accounts, m.usage_for = saved
    return buf.getvalue()


# --------------------------------------------------------------------- helpers

def test_sev_thresholds():
    assert m.sev(None) == "dim"
    assert m.sev(0) == "green"
    assert m.sev(49) == "green"
    assert m.sev(50) == "amber"      # AMBER_AT
    assert m.sev(84) == "amber"
    assert m.sev(85) == "red"        # RED_AT
    assert m.sev(150) == "red"


def test_bar_clamps():
    assert m.bar(None) == "─" * 10
    assert m.bar(0) == "░" * 10
    assert m.bar(100) == "█" * 10
    assert m.bar(150) == "█" * 10    # clamps above 100
    assert m.bar(-10) == "░" * 10    # clamps below 0
    assert len(m.bar(37)) == 10


def test_fmt_pct():
    assert m.fmt_pct(None) == "—"
    assert m.fmt_pct(0) == "0%"
    assert m.fmt_pct(54.6) == "55%"


def test_fmt_reset():
    assert m.fmt_reset(None) == ""
    assert m.fmt_reset("not-a-date") == ""
    # a timestamp far in the past reads as resetting
    assert m.fmt_reset("2000-01-01T00:00:00Z") == "resetting now"


def test_to_ms():
    assert m._to_ms(1_700_000_000) == 1_700_000_000_000      # seconds -> ms
    assert m._to_ms(1_700_000_000_000) == 1_700_000_000_000   # already ms
    assert m._to_ms("nonsense") == 0
    assert m._to_ms(None) == 0


def test_slug():
    assert m._slug("Personal") == "personal"
    assert m._slug("a b/c") == "a_b_c"
    assert m._slug("") == "acct"


def test_util():
    assert m.util(None) == (None, None)
    assert m.util({"utilization": 42, "resets_at": "x"}) == (42.0, "x")
    assert m.util({"utilization": "bad"})[0] is None


# ---------------------------------------------------- headline fix: per-model

def test_worst_includes_per_model_limits():
    """The per-account status dot must reflect Opus/Sonnet weekly caps, not just
    five_hour/seven_day — the core QA fix."""
    data = {
        "five_hour": {"utilization": 40},
        "seven_day": {"utilization": 54},
        "seven_day_opus": {"utilization": 91},
        "seven_day_sonnet": {"utilization": 30},
    }
    res = {"ok": True, "data": data, "stale": False, "age": 0, "error": None, "source": "x"}
    _, worst = m.account_lines({"label": "p"}, res)
    assert worst == 91, worst
    assert m.sev(worst) == "red"


def test_account_lines_survives_non_dict_payload():
    res = {"ok": True, "data": ["unexpected"], "stale": False, "age": 0, "error": None, "source": None}
    lines, worst = m.account_lines({"label": "x"}, res)
    assert worst is None
    assert isinstance(lines, list)


def test_sign_out_only_for_oauth():
    data = {"five_hour": {"utilization": 10}}
    res = {"ok": True, "data": data, "stale": False, "age": 0, "error": None, "source": "x"}
    oauth_lines, _ = m.account_lines({"label": "a", "kind": "oauth", "refresh_token": "r"}, res)
    manual_lines, _ = m.account_lines({"label": "b", "credentials_file": "/x"}, res)
    assert any("sign out" in ln for ln in oauth_lines)
    assert not any("sign out" in ln for ln in manual_lines)


# -------------------------------------------- menu bar: current session only

def test_title_pct_is_session_only():
    """The menu-bar number is the rolling 5-hour window and nothing else — a higher
    weekly or per-model cap never replaces it, and never tacks a ⚠ onto it."""
    data = {"five_hour": {"utilization": 20}, "seven_day": {"utilization": 90},
            "seven_day_opus": {"utilization": 99}}
    assert m._title_pct(data) == "20%"
    # …including when every other window is pinned at the ceiling
    assert m._title_pct({"five_hour": {"utilization": 3}, "seven_day": {"utilization": 100},
                         "seven_day_opus": {"utilization": 100}}) == "3%"


def test_title_pct_never_falls_back_to_another_window():
    # no session number -> nothing to show; the weekly must not stand in for it
    assert m._title_pct({"seven_day": {"utilization": 60}}) is None
    assert m._title_pct({}) is None
    assert m._title_pct(["unexpected"]) is None
    assert m._title_pct({"five_hour": {"utilization": "bad"}}) is None


def test_menu_bar_title_shows_session_when_weekly_is_higher():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    out = _render_main({"five_hour": {"utilization": 20}, "seven_day": {"utilization": 96},
                        "seven_day_opus": {"utilization": 99}})
    title = _title_of(out)
    assert title.strip() == "20%", title
    for leaked in ("96", "99", "⚠"):
        assert leaked not in title, title
    # the dropdown still carries the full picture
    assert "weekly" in out and "96%" in out and "Opus" in out


def test_menu_bar_quiet_without_a_session_number():
    """No 5-hour window in the payload -> the subtle icon, not the weekly number."""
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    out = _render_main({"seven_day": {"utilization": 60}})
    title = _title_of(out)
    assert title.strip() == "Claude", title
    assert "60" not in title
    assert "weekly" in out                       # still listed in the dropdown


def test_session_row_labelled_and_first():
    data = {"five_hour": {"utilization": 40}, "seven_day": {"utilization": 54}}
    res = {"ok": True, "data": data, "stale": False, "age": 0, "error": None, "source": "x"}
    lines, _ = m.account_lines({"label": "p"}, res)
    rows = [ln for ln in lines if "[" in ln]
    assert "session" in rows[0] and "40%" in rows[0], rows[0]
    assert "weekly" in rows[1], rows[1]
    assert not any("5-hour" in ln for ln in lines)


def test_no_menu_bar_window_selector():
    """The window selector is gone: session-only, so there is nothing to choose."""
    assert not hasattr(m, "display_mode")
    assert not hasattr(m, "do_set_display")
    assert not hasattr(m, "DISPLAY_MODES")


def test_stale_menu_bar_config_key_is_ignored():
    """Upgraders whose config still says menu_bar: weekly get the session number,
    and the leftover key is left alone rather than rewritten."""
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    cfg_file = os.path.join(tmp, "config.json")
    json.dump({"menu_bar": "weekly", "accounts": [{"label": "work"}]}, open(cfg_file, "w"))
    out = _render_main({"five_hour": {"utilization": 20}, "seven_day": {"utilization": 96}})
    assert _title_of(out).strip() == "20%", _title_of(out)
    assert json.load(open(cfg_file))["menu_bar"] == "weekly"


# ---------------------------------------------------- account collision fix

def test_unique_label_no_clobber():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    os.makedirs(m.ACCOUNTS_DIR, exist_ok=True)
    m._store_tokens("alice", {"access_token": "a", "refresh_token": "r", "expires_in": 3600},
                    email="alice@gmail.com")
    assert m._unique_label("alice", "alice@gmail.com") == "alice"    # same account reuses
    assert m._unique_label("alice", "alice@work.com") == "alice-2"   # different -> no clobber
    m._store_tokens("claude", {"access_token": "a", "refresh_token": "r", "expires_in": 3600},
                    email=None)
    assert m._unique_label("claude", "") == "claude-2"               # email-less collision


# ------------------------------------------------------------- ensure_config

def test_ensure_config_creates_empty_accounts():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    m._ensure_config()
    cfg = json.load(open(os.path.join(tmp, "config.json")))
    assert cfg["accounts"] == []          # keeps welcome + auto-detect intact
    assert "menu_bar" not in cfg          # no window to pick — session only


# --------------------------------------------------- footer: paths are quoted

def test_footer_quotes_paths():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    buf = io.StringIO()
    with redirect_stdout(buf):
        m._footer()
    out = buf.getvalue()
    # rm/open actions must quote param2 so spaces in the path don't break them
    assert 'param2="' in out
    assert "Menu bar shows" not in out    # window selector removed
    assert "set-display" not in out


# ------------------------------------------------------------------- runner

def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:  # noqa: BLE001 - test runner surfaces every failure
            failed += 1
            import traceback
            print(f"✗ {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
