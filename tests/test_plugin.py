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


def _render_main(data, label="personal", extra=()):
    """Run main() against a canned payload and return its stdout, with the account
    lookup and the network stubbed out. `extra` adds more accounts as (label, payload)."""
    payloads = dict([(label, data)] + list(extra))
    saved = (m.load_accounts, m.usage_for)
    m.load_accounts = lambda: [{"label": lbl} for lbl in payloads]
    m.usage_for = lambda acct: {"ok": True, "data": payloads[acct["label"]], "stale": False,
                                "age": 0, "error": None, "source": "stub"}
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            m.main()
    finally:
        m.load_accounts, m.usage_for = saved
    return buf.getvalue()


def _sessions(*pairs):
    """(label, payload) pairs carrying just a session percentage."""
    return [(label, {"five_hour": {"utilization": pct}}) for label, pct in pairs]


def _act(argv, labels):
    """Run a menu action (toggle-account / move-account) against `labels`."""
    saved = (m.load_accounts, sys.argv)
    m.load_accounts = lambda: [{"label": lbl} for lbl in labels]
    sys.argv = argv
    try:
        m.do_toggle_account() if argv[1] == "toggle-account" else m.do_move_account()
    finally:
        m.load_accounts, sys.argv = saved


def _stored_order(tmp):
    """[(label, menu_bar)] as persisted in the config file."""
    cfg = json.load(open(os.path.join(tmp, "config.json")))
    return [(e["label"], e["menu_bar"]) for e in cfg.get("accounts_display", [])]


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


# ------------------------------------------- accounts: order + menu-bar on/off

def _accts(*labels):
    return [{"label": lbl} for lbl in labels]


def test_order_accounts_follows_config():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"accounts_display": [{"label": "work"}, {"label": "personal"}]},
              open(os.path.join(tmp, "config.json"), "w"))
    got = [a["label"] for a in m.order_accounts(_accts("personal", "work"))]
    assert got == ["work", "personal"], got


def test_order_accounts_appends_unlisted_and_skips_unknown():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"accounts_display": [{"label": "gone"}, {"label": "work"}]},
              open(os.path.join(tmp, "config.json"), "w"))
    # 'gone' no longer exists -> skipped; 'new' isn't listed -> keeps its place at the end
    got = [a["label"] for a in m.order_accounts(_accts("personal", "work", "new"))]
    assert got == ["work", "personal", "new"], got


def test_display_prefs_tolerates_hand_edits():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"accounts_display": ["work", {"label": "personal", "menu_bar": False},
                                    {"no_label": 1}, 42, {"label": "x", "menu_bar": "yes"}]},
              open(os.path.join(tmp, "config.json"), "w"))
    assert m._display_prefs() == [("work", True), ("personal", False), ("x", True)]
    assert m.hidden_labels() == {"personal"}          # a bare string means "shown"


def test_no_config_means_no_change():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    accounts = _accts("personal", "work")
    assert [a["label"] for a in m.order_accounts(accounts)] == ["personal", "work"]
    assert m.hidden_labels() == set()


def test_menu_bar_follows_the_configured_order():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"accounts_display": [{"label": "work"}, {"label": "personal"}]},
              open(os.path.join(tmp, "config.json"), "w"))
    (wl, wd), (pl, pd) = _sessions(("work", 40), ("personal", 96))
    out = _render_main(pd, label=pl, extra=[(wl, wd)])
    assert _title_of(out).strip() == "W 40% · P 96%", _title_of(out)


def test_menu_bar_skips_disabled_accounts_and_keeps_order():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"accounts_display": [{"label": "work", "menu_bar": True},
                                    {"label": "personal", "menu_bar": False}]},
              open(os.path.join(tmp, "config.json"), "w"))
    (wl, wd), (pl, pd) = _sessions(("work", 40), ("personal", 96))
    out = _render_main(pd, label=pl, extra=[(wl, wd)])
    # one account left showing -> the single-account format: just its percentage
    assert _title_of(out).strip() == "40%", _title_of(out)
    assert "96" not in _title_of(out)
    # …but personal keeps its full section in the dropdown, flagged and ordered
    body = out.splitlines()
    assert any("personal" in ln and "hidden from menu bar" in ln for ln in body)
    assert any("96%" in ln for ln in body)
    assert body.index([ln for ln in body if ln.startswith("work")][0]) < \
           body.index([ln for ln in body if ln.startswith("personal")][0])


def test_menu_bar_quiet_when_every_account_is_off():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"accounts_display": [{"label": "personal", "menu_bar": False}]},
              open(os.path.join(tmp, "config.json"), "w"))
    out = _render_main({"five_hour": {"utilization": 96}})
    assert _title_of(out).strip() == "Claude", _title_of(out)
    assert any("96%" in ln for ln in out.splitlines())            # still in the dropdown


def test_toggle_account_roundtrip():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"accounts": [{"label": "work"}]}, open(os.path.join(tmp, "config.json"), "w"))
    _act(["p", "toggle-account", "work"], ["personal", "work"])
    # the first click writes the whole list, so it reads cleanly by hand
    assert _stored_order(tmp) == [("personal", True), ("work", False)]
    _act(["p", "toggle-account", "work"], ["personal", "work"])
    assert _stored_order(tmp) == [("personal", True), ("work", True)]
    # unrelated keys survive
    assert json.load(open(os.path.join(tmp, "config.json")))["accounts"] == [{"label": "work"}]


def test_move_account_reorders_and_clamps():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    labels = ["personal", "work", "side project"]
    _act(["p", "move-account", "side project", "up"], labels)
    assert _stored_order(tmp) == [("personal", True), ("side project", True), ("work", True)]
    _act(["p", "move-account", "personal", "down"], labels)
    assert _stored_order(tmp) == [("side project", True), ("personal", True), ("work", True)]
    # moving the first one up is a no-op, not an error or a wrap-around
    _act(["p", "move-account", "side project", "up"], labels)
    assert _stored_order(tmp) == [("side project", True), ("personal", True), ("work", True)]


def test_move_preserves_the_on_off_state():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    _act(["p", "toggle-account", "work"], ["personal", "work"])
    _act(["p", "move-account", "work", "up"], ["personal", "work"])
    assert _stored_order(tmp) == [("work", False), ("personal", True)]


def test_display_actions_reject_bad_input():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    for argv in (["p", "toggle-account", "nope"], ["p", "toggle-account"],
                 ["p", "move-account", "personal", "sideways"], ["p", "move-account", "nope", "up"]):
        try:
            _act(argv, ["personal", "work"])
            raise AssertionError(f"expected SystemExit for {argv}")
        except SystemExit:
            pass
    assert not os.path.exists(os.path.join(tmp, "config.json"))    # nothing written


def test_display_actions_leave_a_corrupt_config_alone():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    cfg_file = os.path.join(tmp, "config.json")
    open(cfg_file, "w").write("{broken")
    _act(["p", "toggle-account", "work"], ["personal", "work"])
    _act(["p", "move-account", "work", "up"], ["personal", "work"])
    assert open(cfg_file).read() == "{broken"


def test_accounts_submenu_rendered():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    prefs = [("personal", True), ("side project", False)]
    buf = io.StringIO()
    with redirect_stdout(buf):
        m._footer(_accts("personal", "side project"), prefs)
    out = buf.getvalue()
    assert "Accounts" in out
    assert "-- ✓ personal" in out and "-- ☐ side project" in out
    # labels are quoted, so a space in one doesn't split the action's params
    assert 'param2="side project"' in out
    # ends of the list don't offer a move that goes nowhere
    assert out.count("move up") == 1 and out.count("move down") == 1


def test_footer_without_accounts_has_no_submenu():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    buf = io.StringIO()
    with redirect_stdout(buf):
        m._footer()                    # the welcome screen path
    assert "toggle-account" not in buf.getvalue()


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
