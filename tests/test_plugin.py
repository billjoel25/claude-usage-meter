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
import time
import urllib.error
import urllib.parse
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
    """Point the module's filesystem paths at a throwaway dir — including the
    ~/.claude.json the plan watcher reads, so no test depends on this machine."""
    m.APP_DIR = tmp
    m.CACHE_DIR = os.path.join(tmp, "cache")
    m.ACCOUNTS_DIR = os.path.join(tmp, "accounts")
    m.config_candidates = lambda: [os.path.join(tmp, "config.json")]
    m.config_path = lambda: os.path.join(tmp, "config.json")
    m.CLAUDE_JSON = os.path.join(tmp, "claude.json")


def _write_profile(org="claude_team"):
    """A ~/.claude.json whose oauthAccount reports `org` (None leaves it out)."""
    acct = {"seatTier": "team_tier_1", "organizationName": "Learnyst"}
    if org is not None:
        acct["organizationType"] = org
    json.dump({"oauthAccount": acct}, open(m.CLAUDE_JSON, "w"))


def _title_of(out):
    """The menu-bar text of a rendered dropdown — the first line, minus its
    ` | key=value` params (which carry the base64 icon)."""
    return out.splitlines()[0].split(" | ", 1)[0]


def _render_main(data, label="personal", extra=(), ring=False):
    """Run main() against a canned payload and return its stdout, with the account
    lookup and the network stubbed out. `extra` adds more accounts as (label, payload).

    ring=False turns the week ring off, so the title comes out as macOS text that
    tests can read; the drawn title (the shipped default) has its own tests, which
    check it shows exactly that text."""
    payloads = dict([(label, data)] + list(extra))
    saved = (m.load_accounts, m.usage_for, m.WEEK_RING)
    m.load_accounts = lambda: [{"label": lbl} for lbl in payloads]
    m.usage_for = lambda acct: {"ok": True, "data": payloads[acct["label"]], "stale": False,
                                "age": 0, "error": None, "source": "stub"}
    m.WEEK_RING = ring
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            m.main()
    finally:
        m.load_accounts, m.usage_for, m.WEEK_RING = saved
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
    assert m.sev(85) == "amber"      # no red tier by default…
    assert m.sev(150) == "amber"     # …however close to the ceiling
    saved = m.RED_AT
    m.RED_AT = 85                    # opt back in, and red returns
    try:
        assert m.sev(84) == "amber"
        assert m.sev(85) == "red"
    finally:
        m.RED_AT = saved


def _screenshot_case(err=None):
    """The dropdown that prompted the color changes: Work, session 21%, weekly 85%
    with 33h to run — plus a maxed Opus row, the loudest thing usage can show."""
    data = {"five_hour": {"utilization": 21, "resets_at": "2099-01-01T00:00:00Z"},
            "seven_day": {"utilization": 85, "resets_at": "2099-01-01T00:00:00Z"},
            "seven_day_opus": {"utilization": 100}}
    return {"ok": True, "data": data, "stale": False, "age": 0, "error": err, "source": "x"}


def test_usage_is_plain_black_by_default():
    """Every row, the account header and an error line: plain text, whatever the
    number. The percentage and its reset countdown say how close you are."""
    _isolate(tempfile.mkdtemp())
    lines, _ = m.account_lines({"label": "Work"}, _screenshot_case(err="429 — rate limited"))
    text = m.color_param("text")
    for c in ("green", "amber", "red"):
        for ln in lines:
            assert m.color_param(c) not in ln and m.sf(c) not in ln, (c, ln)
    for needle in ("Work", "21%", "85%", "100%", "429"):
        hit = [ln for ln in lines if needle in ln]
        assert hit and all(f"color={text}" in ln for ln in hit), (needle, hit)
    # set explicitly, not left off: SwiftBar draws action-less items gray
    assert m.COLORS["text"] == ("#000000", "#ffffff")


def test_status_colors_on_request():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    json.dump({"colors": "status"}, open(os.path.join(tmp, "config.json"), "w"))
    lines, _ = m.account_lines({"label": "Work"}, _screenshot_case())
    assert any("21%" in ln and m.color_param("green") in ln for ln in lines), lines
    assert any("85%" in ln and m.color_param("amber") in ln for ln in lines), lines
    for ln in lines:                       # still no red unless RED_AT is set
        assert m.color_param("red") not in ln and m.sf("red") not in ln, ln


def test_color_mode_config():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    cfg = os.path.join(tmp, "config.json")
    assert m.color_mode() == "neutral"                     # no config at all
    json.dump({"colors": "status"}, open(cfg, "w"))
    assert m.color_mode() == "status"
    for junk in ("rainbow", 1, None, ["status"]):
        json.dump({"colors": junk}, open(cfg, "w"))
        assert m.color_mode() == "neutral", junk          # anything else: neutral
    open(cfg, "w").write("{broken")
    assert m.color_mode() == "neutral"


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
    assert m.sev(worst) == "amber"   # loud enough; usage has no red tier


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


# ------------------------------------------------ menu bar: session · weekly

def test_title_pct_is_session_then_weekly():
    """'2% · 30%': session first, weekly second, always in that order, so a higher
    weekly can never be read as the session. Per-model caps never appear, and no ⚠."""
    data = {"five_hour": {"utilization": 20}, "seven_day": {"utilization": 90},
            "seven_day_opus": {"utilization": 99}}
    assert m._title_pct(data) == "20% · 90%"
    assert m._title_pct({"five_hour": {"utilization": 2.4},
                         "seven_day": {"utilization": 29.6}}) == "2% · 30%"
    # …including when every other window is pinned at the ceiling
    assert m._title_pct({"five_hour": {"utilization": 3}, "seven_day": {"utilization": 100},
                         "seven_day_opus": {"utilization": 100}}) == "3% · 100%"


def test_title_pct_without_a_weekly_shows_the_session_alone():
    assert m._title_pct({"five_hour": {"utilization": 20}}) == "20%"
    assert m._title_pct({"five_hour": {"utilization": 20},
                         "seven_day": {"utilization": "bad"}}) == "20%"


def test_title_pct_never_falls_back_to_another_window():
    # no session number -> nothing to show; the weekly must not stand in for it
    assert m._title_pct({"seven_day": {"utilization": 60}}) is None
    assert m._title_pct({}) is None
    assert m._title_pct(["unexpected"]) is None
    assert m._title_pct({"five_hour": {"utilization": "bad"}}) is None


def test_menu_bar_title_is_session_then_weekly():
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    out = _render_main({"five_hour": {"utilization": 20}, "seven_day": {"utilization": 96},
                        "seven_day_opus": {"utilization": 99}})
    title = _title_of(out)
    assert title.strip() == "20% · 96%", title
    for leaked in ("99", "⚠"):
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
    """The window selector is gone: session · weekly is fixed, nothing to choose."""
    assert not hasattr(m, "display_mode")
    assert not hasattr(m, "do_set_display")
    assert not hasattr(m, "DISPLAY_MODES")


def test_stale_menu_bar_config_key_is_ignored():
    """Upgraders whose config still says menu_bar: weekly get session · weekly like
    everyone else, and the leftover key is left alone rather than rewritten."""
    tmp = tempfile.mkdtemp()
    _isolate(tmp)
    cfg_file = os.path.join(tmp, "config.json")
    json.dump({"menu_bar": "weekly", "accounts": [{"label": "work"}]}, open(cfg_file, "w"))
    out = _render_main({"five_hour": {"utilization": 20}, "seven_day": {"utilization": 96}})
    assert _title_of(out).strip() == "20% · 96%", _title_of(out)
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
    assert _title_of(out).strip() == "W 40%   P 96%", _title_of(out)


def test_menu_bar_with_several_accounts_keeps_each_pair_together():
    """' · ' joins an account's session and weekly, so accounts are told apart by
    their initials and a wider gap — never by the same dot."""
    _isolate(tempfile.mkdtemp())
    out = _render_main({"five_hour": {"utilization": 40}, "seven_day": {"utilization": 10}},
                       label="work",
                       extra=[("personal", {"five_hour": {"utilization": 96},
                                            "seven_day": {"utilization": 54}})])
    assert _title_of(out).strip() == "W 40% · 10%   P 96% · 54%", _title_of(out)


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
    # the rm action must quote param2 so a space in the path doesn't break it
    assert 'param2="' in out
    assert "Menu bar shows" not in out    # window selector removed
    assert "set-display" not in out


def test_footer_is_just_the_actions():
    """No About / setup submenu, config path, or project link — only things to do."""
    _isolate(tempfile.mkdtemp())
    buf = io.StringIO()
    with redirect_stdout(buf):
        m._footer([{"label": "Work"}], [])
    titles = [ln.split(" | ")[0].strip() for ln in buf.getvalue().splitlines()
              if not ln.startswith("--")]            # top-level items only
    assert titles == ["➕ Add Claude account…", "Refresh now",
                      "Force refresh (clear cache)", "Accounts"], titles
    for gone in ("About / setup", "Edit config file", "Project on GitHub", "Config:"):
        assert gone not in buf.getvalue(), gone


def test_swiftbar_default_items_hidden():
    """SwiftBar appends About, Updated N ago, Disable Plugin, Run in Terminal and its
    own submenu to every plugin's menu unless the header says not to."""
    header = open(PLUGIN, encoding="utf-8").read().split("\nimport ", 1)[0]
    for tag in ("hideAbout", "hideRunInTerminal", "hideLastUpdated",
                "hideDisablePlugin", "hideSwiftBar"):
        assert f"<swiftbar.{tag}>true</swiftbar.{tag}>" in header, tag


# ------------------------------------------- cache: expires and clears on its own

def _write_cache(label, fetched_ago=0, session_reset="2099-01-01T00:00:00Z", pct=57):
    os.makedirs(m.CACHE_DIR, exist_ok=True)
    json.dump({"fetched_at": time.time() - fetched_ago, "source": "file",
               "data": {"five_hour": {"utilization": pct, "resets_at": session_reset},
                        "seven_day": {"utilization": 24,
                                      "resets_at": "2099-01-01T00:00:00Z"}}},
              open(m.cache_path(label), "w"))


def _stub_network(token=("t", None, "file"), fetcher=None, oauth=None):
    """Swap out token lookup and the HTTP call. Returns what to hand _restore."""
    saved = (m.get_token, m.fetch_usage, m._oauth_token)
    m.get_token = lambda a: token
    m.fetch_usage = fetcher or (lambda t: {"five_hour": {"utilization": 1}})
    if oauth:
        m._oauth_token = oauth
    return saved


def _restore(saved):
    m.get_token, m.fetch_usage, m._oauth_token = saved


def _http401(_token):
    raise urllib.error.HTTPError("https://x", 401, "unauthorized", None, None)


def test_stale_cache_carries_a_blip_but_not_forever():
    _isolate(tempfile.mkdtemp())
    saved = _stub_network(token=(None, None, "not logged in"))
    try:
        _write_cache("p", fetched_ago=300)             # 5 min old, windows still live
        res = m.usage_for({"label": "p"})
        assert res["ok"] and res["stale"], res         # carried through the failure
        assert os.path.exists(m.cache_path("p"))
        _write_cache("p", fetched_ago=m.STALE_MAX + 60)
        res = m.usage_for({"label": "p"})
        assert not res["ok"], res                      # too old to stand in
        assert not os.path.exists(m.cache_path("p"))   # and cleared without being asked
    finally:
        _restore(saved)


def test_cache_expires_once_its_window_has_reset():
    """The real-world failure: 57% sitting in the menu bar beside 'resetting now'.
    The window it described is over, so the number is wrong however fresh the fetch."""
    _isolate(tempfile.mkdtemp())
    saved = _stub_network(token=(None, None, "not logged in"))
    try:
        _write_cache("p", fetched_ago=5, session_reset="2000-01-01T00:00:00Z")
        res = m.usage_for({"label": "p"})              # inside CACHE_TTL, still dropped
        assert not res["ok"], res
        assert not os.path.exists(m.cache_path("p"))
    finally:
        _restore(saved)


def test_rate_limiting_keeps_the_cache():
    """429 is transient by definition — exactly what a stale cache is for."""
    _isolate(tempfile.mkdtemp())

    def limited(_t):
        raise urllib.error.HTTPError("https://x", 429, "slow down", None, None)

    saved = _stub_network(fetcher=limited)
    try:
        _write_cache("p", fetched_ago=300)
        res = m.usage_for({"label": "p"})
        assert res["ok"] and res["stale"]
        assert "429" in res["error"]
        assert os.path.exists(m.cache_path("p"))
    finally:
        _restore(saved)


def test_401_self_heals_when_the_refresh_token_still_works():
    """An access token can be dead while the refresh behind it works. That should
    recover by itself, not ask for a sign-out and re-add."""
    _isolate(tempfile.mkdtemp())
    tried = []

    def fetch(tok):
        tried.append(tok)
        if tok == "dead":
            _http401(tok)
        return {"five_hour": {"utilization": 12}}

    saved = _stub_network(token=("dead", None, "signed in"), fetcher=fetch,
                          oauth=lambda a, force=False: ("fresh", None, "signed in"))
    try:
        res = m.usage_for({"label": "p", "refresh_token": "r"})
        assert res["ok"] and not res["stale"], res
        assert res["data"]["five_hour"]["utilization"] == 12
        assert tried == ["dead", "fresh"], tried       # exactly one retry
        assert os.path.exists(m.cache_path("p"))       # the live reading is cached
    finally:
        _restore(saved)


def test_401_that_cannot_heal_drops_the_cache_without_a_second_request():
    _isolate(tempfile.mkdtemp())
    tried = []

    def fetch(tok):
        tried.append(tok)
        _http401(tok)

    saved = _stub_network(token=("dead", None, "signed in"), fetcher=fetch,
                          oauth=lambda a, force=False: ("dead", None, "signed in"))
    try:
        # older than CACHE_TTL so a fetch is attempted, younger than STALE_MAX so
        # only the 401 itself can be what drops it
        _write_cache("p", fetched_ago=m.CACHE_TTL + 60)
        res = m.usage_for({"label": "p", "refresh_token": "r"})
        assert not res["ok"] and "401" in res["error"], res
        assert not os.path.exists(m.cache_path("p"))   # rejected token -> numbers go
        assert tried == ["dead"], tried                # no pointless repeat call
    finally:
        _restore(saved)


def test_401_without_any_refresh_token_just_reports():
    _isolate(tempfile.mkdtemp())
    saved = _stub_network(token=("dead", None, "keychain"), fetcher=_http401)
    try:
        res = m.usage_for({"label": "p"})
        assert not res["ok"] and "401" in res["error"]
        assert "run `claude`" in res["error"]          # not an in-app sign-in
    finally:
        _restore(saved)


def test_unusable_cache_file_is_cleaned_up():
    _isolate(tempfile.mkdtemp())
    saved = _stub_network(token=(None, None, "not logged in"))
    try:
        os.makedirs(m.CACHE_DIR, exist_ok=True)
        open(m.cache_path("p"), "w").write("{broken")
        res = m.usage_for({"label": "p"})
        assert not res["ok"]
        assert not os.path.exists(m.cache_path("p"))
    finally:
        _restore(saved)


def test_a_live_fetch_always_wins():
    _isolate(tempfile.mkdtemp())
    saved = _stub_network(fetcher=lambda t: {"five_hour": {"utilization": 3}})
    try:
        _write_cache("p", fetched_ago=m.STALE_MAX + 60, pct=99)
        res = m.usage_for({"label": "p"})
        assert res["ok"] and not res["stale"]
        assert res["data"]["five_hour"]["utilization"] == 3
    finally:
        _restore(saved)


def test_expired_numbers_say_so_rather_than_blaming_the_login():
    res = {"ok": False, "data": None, "stale": False, "age": None,
           "error": "TimeoutError", "source": None}
    lines, _ = m.account_lines({"label": "p"}, res)
    assert any("cached numbers had expired" in ln for ln in lines), lines
    res["error"] = "401 — sign-in invalid, re-add the account"
    lines, _ = m.account_lines({"label": "p"}, res)
    assert any("Not logged into this account" in ln for ln in lines), lines


def test_windows_reset_detection():
    assert m._windows_reset({"five_hour": {"resets_at": "2000-01-01T00:00:00Z"}}, time.time())
    assert not m._windows_reset({"five_hour": {"resets_at": "2099-01-01T00:00:00Z"}}, time.time())
    assert not m._windows_reset({"five_hour": {"utilization": 5}}, time.time())   # no date
    assert not m._windows_reset({"five_hour": {"resets_at": "nonsense"}}, time.time())
    assert not m._windows_reset(None, time.time())


# ---------------------------------------------------------------- session pie

def _filtered_png(w, rows, kinds):
    """An RGBA PNG whose rows use the given PNG filter types — a reference encoder,
    so the plugin's decoder gets checked on every filter, not only the logo's."""
    import struct as st
    import zlib as zl

    def chunk(tag, body):
        return st.pack(">I", len(body)) + tag + body + st.pack(">I", zl.crc32(tag + body) & 0xFFFFFFFF)

    out, prev = bytearray(), bytearray(w * 4)
    for kind, row in zip(kinds, rows):
        enc = bytearray(len(row))
        for x in range(len(row)):
            a = row[x - 4] if x >= 4 else 0
            b, c = prev[x], (prev[x - 4] if x >= 4 else 0)
            if kind == 0:
                p = 0
            elif kind == 1:
                p = a
            elif kind == 2:
                p = b
            elif kind == 3:
                p = (a + b) // 2
            else:
                q = a + b - c
                pa, pb, pc = abs(q - a), abs(q - b), abs(q - c)
                p = a if pa <= pb and pa <= pc else b if pb <= pc else c
            enc[x] = (row[x] - p) & 255
        out += bytes([kind]) + enc
        prev = row
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", st.pack(">IIBBBBB", w, len(rows), 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zl.compress(bytes(out))) + chunk(b"IEND", b""))


def test_png_decoder_handles_every_filter():
    w = 7
    rows = [bytearray((x * 37 + y * 101 + 13) % 256 for x in range(w * 4)) for y in range(10)]
    kinds = [0, 1, 2, 3, 4, 4, 3, 2, 1, 0]
    dw, dh, got = m._png_decode_rgba(_filtered_png(w, rows, kinds))
    assert (dw, dh) == (w, len(rows))
    assert [bytes(r) for r in got] == [bytes(r) for r in rows]


def test_png_encoder_round_trips():
    rows = [bytearray((x * 11 + y * 29) % 256 for x in range(5 * 4)) for y in range(3)]
    w, h, got = m._png_decode_rgba(m._png_encode_rgba(5, 3, rows))
    assert (w, h) == (5, 3) and [bytes(r) for r in got] == [bytes(r) for r in rows]


def test_logo_decodes_to_the_verified_pixels():
    """Pinned to Pillow's decode of the same PNG, checked when this was written."""
    import base64
    import hashlib
    w, h, rows = m._png_decode_rgba(base64.b64decode(m.CLAUDE_ICON))
    assert (w, h) == (52, 40)
    assert hashlib.sha256(b"".join(bytes(r) for r in rows)).hexdigest() == \
        "85a97a11b8617cbe817bdd79dbd980caf8ec8da4510283d92847bc46197ce4bc"


def test_pie_fills_clockwise_from_twelve():
    import math
    s = m.PIE_PX
    c = s / 2

    def at(alpha, degrees_from_12, radius):
        """Coverage of the pixel at a clock angle and distance from the centre."""
        t = math.radians(degrees_from_12)
        return alpha[int(c - radius * math.cos(t))][int(c + radius * math.sin(t))]

    r_out = c - 0.5                                  # the pie's geometry, from its constants
    r_in = r_out - m.PIE_RING
    inside = (r_in - m.PIE_GAP) * 0.6                # well within the slice
    rim = (r_in + r_out) / 2                         # the middle of the outline

    empty = m._pie_alpha(s, None)
    assert at(empty, 0, rim) == 1 and at(empty, 0, 0) == 0      # outline only
    assert m._pie_alpha(s, 0.0) == empty                        # fresh session looks the same
    early = m._pie_alpha(s, 0.07)                               # 7% = 25° of slice
    assert at(early, 10, inside) == 1 and at(early, 90, inside) == 0
    half = m._pie_alpha(s, 0.5)                                 # 12 round to 6, right side
    assert at(half, 90, inside) == 1 and at(half, 270, inside) == 0
    full = m._pie_alpha(s, 1.0)                                 # a full disc: reset is due
    assert at(full, 270, inside) == 1 and at(full, 0, 0) == 1
    for alpha in (empty, early, half, full):                    # the outline never moves
        assert all(at(alpha, deg, rim) == 1 for deg in (0, 90, 180, 270))


def test_session_elapsed():
    now = 1_800_000_000

    def five(left_s):
        from datetime import datetime, timezone
        iso = datetime.fromtimestamp(now + left_s, timezone.utc).isoformat()
        return {"five_hour": {"utilization": 9, "resets_at": iso}}

    assert abs(m._session_elapsed(five(160 * 60), now) - 140 / 300) < 1e-9   # 2h40m left
    assert m._session_elapsed(five(m.SESSION_SECONDS + 60), now) == 0.0      # clamped
    assert m._session_elapsed(five(-60), now) is None           # window already over
    assert m._session_elapsed({"five_hour": {"utilization": 9}}, now) is None
    assert m._session_elapsed(["unexpected"], now) is None


def test_menu_bar_title_carries_the_pie():
    import base64
    import datetime as dt
    _isolate(tempfile.mkdtemp())
    soon = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=160)).isoformat()
    out = _render_main({"five_hour": {"utilization": 22, "resets_at": soon},
                        "seven_day": {"utilization": 33}})
    first = out.splitlines()[0]
    assert first.startswith("22% · 33% | templateImage="), first[:40]
    icon = first.split("templateImage=", 1)[1].split()[0]
    assert icon != m.CLAUDE_ICON
    w, h, rows = m._png_decode_rgba(base64.b64decode(icon))
    assert (w, h) == (m.PIE_PX + m.PIE_PAD, m.PIE_PX), (w, h)     # the pie alone, no logo
    alpha = [[row[i] for i in range(3, len(row), 4)] for row in rows]
    assert any(a for r in alpha for a in r[:m.PIE_PX])           # pie pixels present
    assert not any(a for r in alpha for a in r[m.PIE_PX:])       # padding before the numbers


def test_menu_bar_pie_follows_the_first_account_shown():
    import datetime as dt
    _isolate(tempfile.mkdtemp())
    now = dt.datetime.now(dt.timezone.utc)
    first = {"five_hour": {"utilization": 5, "resets_at": (now + dt.timedelta(hours=4)).isoformat()}}
    second = {"five_hour": {"utilization": 9, "resets_at": (now + dt.timedelta(minutes=20)).isoformat()}}
    out = _render_main(first, label="work", extra=[("personal", second)])
    icon = out.splitlines()[0].split("templateImage=", 1)[1].split()[0]
    assert icon == m._title_icon(first) != m._title_icon(second)


def test_title_icon_failure_falls_back_quietly():
    """If drawing the pie fails: no image while the logo is off, the plain logo
    when it's on — and the numbers still show either way."""
    _isolate(tempfile.mkdtemp())
    saved = (m.menu_icon, m.MENU_LOGO)
    m.menu_icon = lambda elapsed: 1 / 0
    try:
        assert m._title_icon({"five_hour": {"utilization": 5}}) is None
        out = _render_main({"five_hour": {"utilization": 5}, "seven_day": {"utilization": 9}})
        assert out.splitlines()[0].startswith("5% · 9% | size=11"), out.splitlines()[0][:40]
        m.MENU_LOGO = True
        assert m._title_icon({"five_hour": {"utilization": 5}}) == m.CLAUDE_ICON
    finally:
        m.menu_icon, m.MENU_LOGO = saved


def test_quiet_menu_bar_has_no_icon_while_the_logo_is_off():
    """No session number at all -> just 'Claude', dim; no pie, no logo."""
    _isolate(tempfile.mkdtemp())
    out = _render_main({"seven_day": {"utilization": 60}})
    first = out.splitlines()[0]
    assert first.startswith("Claude | ") and "templateImage=" not in first, first[:60]


def test_logo_comes_back_with_the_switch():
    """MENU_LOGO = True restores the Claude logo in front of the pie, and on the
    quiet and welcome titles."""
    import base64
    _isolate(tempfile.mkdtemp())
    saved = m.MENU_LOGO
    m.MENU_LOGO = True
    try:
        w, h, _ = m._png_decode_rgba(base64.b64decode(m.menu_icon(0.5)))
        assert (w, h) == (52 + m.PIE_SPACE + m.PIE_PX + m.PIE_PAD, 40), (w, h)
        out = _render_main({"seven_day": {"utilization": 60}})
        assert f"templateImage={m.CLAUDE_ICON} " in out.splitlines()[0]
        buf = io.StringIO()
        with redirect_stdout(buf):
            m._welcome()
        assert f"templateImage={m.CLAUDE_ICON} " in buf.getvalue().splitlines()[0]
    finally:
        m.MENU_LOGO = saved


# ---------------------------------------- week ring + drawn numbers (the default)

def _alpha_of(b64):
    """(width, height, alpha rows) of a base64 template PNG."""
    import base64
    w, h, rows = m._png_decode_rgba(base64.b64decode(b64))
    return w, h, [[row[i] for i in range(3, len(row), 4)] for row in rows]


def _clock(alpha, size, degrees_from_12, radius, x0=0, y0=0):
    """The pixel at a clock angle and distance from the centre of a size x size
    glyph whose top-left corner sits at (x0, y0)."""
    import math
    c = size / 2
    t = math.radians(degrees_from_12)
    return alpha[y0 + int(c - radius * math.cos(t))][x0 + int(c + radius * math.sin(t))]


def _drawn_icon(out):
    return out.splitlines()[0].split("templateImage=", 1)[1].split()[0]


def test_glyph_atlas_has_every_title_character():
    """Everything the title can print — digits, '%', ' · ' — is in the atlas, each
    cell inside it, inked, and clear of its neighbours."""
    w, h, alpha = _alpha_of(m.GLYPH_ATLAS)
    assert h == m.GLYPH_H
    for ch in "0123456789%·":
        x, cw, advance = m.GLYPHS[ch]
        assert 0 <= x and x + cw <= w and 0 < advance <= cw, ch
        assert any(a for row in alpha for a in row[x:x + cw]), ch
    cells = sorted(m.GLYPHS[ch][:2] for ch in "0123456789%·")
    assert all(a[0] + a[1] <= b[0] for a, b in zip(cells, cells[1:]))
    assert m.GLYPHS[" "][2] > 0                          # a space only advances


def test_drawn_numbers_match_the_menu_bar_text():
    """'52% · 38%' as macOS sets it in the menu bar measures 112 x 16 px; the drawn
    one must stay that size. Pinned, so changing the atlas is a deliberate act."""
    import hashlib
    w, rows = m._text_alpha("52% · 38%")
    assert len(rows) == m.GLYPH_H and all(len(r) == w for r in rows)
    inked = [y for y, r in enumerate(rows) if any(r)]
    assert inked[-1] + 1 - inked[0] == 16, inked         # 16px digits: 11pt at @2x
    assert abs(w - 112) <= 4, w
    assert hashlib.sha256(bytes(v for r in rows for v in r)).hexdigest() == \
        "5a2cf7faaeaedab90aff2719f753e3f55a238067937e26b7c2af76b08e4fdb2f"


def test_plugin_carries_the_glyph_license():
    """The installer copies the plugin file alone, so the atlas's OFL travels inside
    it — word for word what licenses/Inter-OFL.txt says."""
    lines = open(PLUGIN, encoding="utf-8").read().split("\n")
    start = lines.index("# >>> licenses/Inter-OFL.txt") + 1
    carried = "\n".join(ln[2:] if ln.startswith("# ") else ln.lstrip("#") for ln in lines[start:])
    with open(os.path.join(HERE, "..", "licenses", "Inter-OFL.txt"), encoding="utf-8") as f:
        assert carried.strip() == f.read().strip()
    assert "Copyright 2016-2023 The Inter Project Authors" in carried
    assert "SIL OPEN FONT LICENSE" in carried


def test_text_alpha_unknown_characters_advance_like_a_space():
    assert m._text_alpha("5?5") == m._text_alpha("5 5")
    assert m._text_alpha("") == (0, [[] for _ in range(m.GLYPH_H)])
    assert m._text_alpha("   ")[0] == 0


def test_week_elapsed():
    now = 1_800_000_000

    def seven(left_s):
        from datetime import datetime, timezone
        iso = datetime.fromtimestamp(now + left_s, timezone.utc).isoformat()
        return {"seven_day": {"utilization": 9, "resets_at": iso}}

    assert abs(m._week_elapsed(seven(3.5 * 86400), now) - 0.5) < 1e-9     # 3d 12h left
    assert m._week_elapsed(seven(m.WEEK_SECONDS + 60), now) == 0.0        # clamped
    assert m._week_elapsed(seven(-60), now) is None             # already reset
    assert m._week_elapsed({"seven_day": {"utilization": 9}}, now) is None
    # the session's clock never stands in for the week's
    assert m._week_elapsed({"five_hour": {"utilization": 9,
                                          "resets_at": "2099-01-01T00:00:00Z"}}, now) is None
    assert m._week_elapsed(["unexpected"], now) is None


def test_day_ring_fills_a_day_at_a_time_from_twelve():
    """Seven segments, 12 o'clock first and clockwise: the part of the week gone is
    bright, the rest dim, with a clear gap between days and nothing in the middle."""
    s = m.RING_PX
    mid = s / 2 - 0.5 - m.RING_BAND / 2                  # the middle of the band
    day = 360 / 7

    def at(alpha, deg, radius=mid):
        return _clock(alpha, s, deg, radius)

    def dim(v):
        return abs(v - m.RING_DIM) < 1e-6

    fresh = m._day_ring_alpha(s, None)
    assert all(dim(at(fresh, (k + 0.5) * day)) for k in range(7))     # all still to come
    assert all(at(fresh, k * day) == 0 for k in range(7))             # gaps between days
    assert at(fresh, 0, 0) == 0 and at(fresh, 0, mid - m.RING_BAND) == 0   # hollow
    assert m._day_ring_alpha(s, 0.0) == fresh
    half = m._day_ring_alpha(s, 0.5)                     # 3½ days gone
    assert all(at(half, (k + 0.5) * day) == 1 for k in range(3))
    assert all(dim(at(half, (k + 0.5) * day)) for k in range(4, 7))
    assert at(half, 3.3 * day) == 1 and dim(at(half, 3.7 * day))      # midway through day 4
    full = m._day_ring_alpha(s, 1.0)                     # the weekly reset is due
    assert all(at(full, (k + 0.5) * day) == 1 for k in range(7))


def test_drawn_title_is_the_plain_title_redrawn():
    """Shipped default, one account: pie, numbers and week ring as one template
    image — and the numbers are exactly the text the plain title would show."""
    assert m.WEEK_RING is True
    _isolate(tempfile.mkdtemp())
    data = {"five_hour": {"utilization": 20}, "seven_day": {"utilization": 96},
            "seven_day_opus": {"utilization": 99}}
    text = _title_of(_render_main(data))
    assert text == "20% · 96%", text
    first = _render_main(data, ring=True).splitlines()[0]
    assert first == f"| templateImage={m.title_image(data, text)}", first[:60]

    w, h, alpha = _alpha_of(_drawn_icon(first))
    tw, glyphs = m._text_alpha(text)
    x_text = m.PIE_PX + m.TEXT_GAP
    x_ring = x_text + tw + m.TEXT_GAP
    assert (w, h) == (x_ring + m.RING_PX, m.PIE_PX), (w, h)
    top = h // 2 - m.GLYPH_CAP_MID
    assert [r[x_text:x_text + tw] for r in alpha[top:top + m.GLYPH_H]] == glyphs
    rows = [y for y, r in enumerate(alpha) if any(r[x_text:x_text + tw])]
    assert abs((rows[0] + rows[-1] + 1) / 2 - h / 2) <= 1, rows      # level with the pie
    rows = [y for y, r in enumerate(alpha) if any(r[x_ring:])]
    assert (rows[0] + rows[-1] + 1) / 2 == h / 2, rows                # the ring too…
    assert m.RING_PX < m.PIE_PX                                        # …a tad smaller

    def inked(x0, x1):
        return any(a for r in alpha for a in r[x0:x1])

    assert inked(0, m.PIE_PX) and inked(x_ring, w)               # pie, ring
    assert not inked(m.PIE_PX, x_text) and not inked(x_text + tw, x_ring)   # the gaps
    # pie -> numbers -> ring, ink to ink: the 15px (7.5pt) the pie already had from
    # the numbers in macOS's own text, so switching over moves nothing
    cols = [x for x in range(w) if inked(x, x + 1)]
    gaps = [b - a - 1 for a, b in zip(cols, cols[1:]) if b - a > 1]
    assert gaps[0] == gaps[-1] == 15, gaps


def test_drawn_title_leaves_the_ring_off_without_a_weekly():
    _isolate(tempfile.mkdtemp())
    out = _render_main({"five_hour": {"utilization": 5}}, ring=True)
    w, h, _ = _alpha_of(_drawn_icon(out))
    assert (w, h) == (m.PIE_PX + m.TEXT_GAP + m._text_alpha("5%")[0], m.PIE_PX), (w, h)


def test_drawn_ring_follows_the_weekly_reset():
    """3½ days to the weekly reset: the ring's right half is bright and its left
    dim — the week's own clock, whatever the session's says."""
    import datetime as dt
    _isolate(tempfile.mkdtemp())
    now = dt.datetime.now(dt.timezone.utc)
    data = {"five_hour": {"utilization": 5,
                          "resets_at": (now + dt.timedelta(minutes=30)).isoformat()},
            "seven_day": {"utilization": 9,
                          "resets_at": (now + dt.timedelta(days=3.5)).isoformat()}}
    w, h, alpha = _alpha_of(_drawn_icon(_render_main(data, ring=True)))
    mid = m.RING_PX / 2 - 0.5 - m.RING_BAND / 2
    day = 360 / 7

    def ring(deg):
        return _clock(alpha, m.RING_PX, deg, mid, x0=w - m.RING_PX, y0=(h - m.RING_PX) // 2)

    assert ring(1.5 * day) == 255, ring(1.5 * day)
    assert ring(5.5 * day) == round(255 * m.RING_DIM), ring(5.5 * day)


def test_drawn_title_only_for_one_account_with_a_session():
    """Several accounts keep macOS's own text after the pie, initials and all, with
    no ring; the quiet title stays just 'Claude'."""
    _isolate(tempfile.mkdtemp())
    out = _render_main({"five_hour": {"utilization": 40}, "seven_day": {"utilization": 10}},
                       label="work", extra=[("personal", {"five_hour": {"utilization": 5}})],
                       ring=True)
    assert out.splitlines()[0].startswith("W 40% · 10%   P 5% | templateImage="), \
        out.splitlines()[0][:60]
    out = _render_main({"seven_day": {"utilization": 60}}, ring=True)
    assert _title_of(out).strip() == "Claude", _title_of(out)


def test_drawn_title_failure_falls_back_to_macos_text():
    _isolate(tempfile.mkdtemp())
    saved = m.title_image
    m.title_image = lambda data, text: 1 / 0
    try:
        out = _render_main({"five_hour": {"utilization": 5}, "seven_day": {"utilization": 9}},
                           ring=True)
    finally:
        m.title_image = saved
    first = out.splitlines()[0]
    assert first.startswith("5% · 9% | templateImage="), first[:40]      # pie + text


def test_drawn_title_puts_the_logo_first_with_the_switch():
    saved = m.MENU_LOGO
    m.MENU_LOGO = True
    try:
        w, h, _ = _alpha_of(m.title_image({"five_hour": {"utilization": 5},
                                           "seven_day": {"utilization": 9}}, "5% · 9%"))
    finally:
        m.MENU_LOGO = saved
    tw = m._text_alpha("5% · 9%")[0]
    assert (w, h) == (52 + m.PIE_SPACE + m.PIE_PX + m.TEXT_GAP + tw + m.TEXT_GAP + m.RING_PX,
                      40), (w, h)


# --------------------------------------------------- plan-change notification

def _watch(sent):
    """watch_plan() with notify() swapped for a recorder."""
    saved = m.notify
    m.notify = lambda title, body: sent.append((title, body)) or "SwiftBar"
    try:
        return m.watch_plan()
    finally:
        m.notify = saved


def test_plan_first_run_records_quietly():
    _isolate(tempfile.mkdtemp())
    _write_profile("claude_team")
    sent = []
    assert _watch(sent) is None and sent == []
    assert json.load(open(m.plan_state_path())) == {"organizationType": "claude_team"}


def test_plan_notifies_once_when_the_org_leaves_team():
    """The one thing asked for. The Enterprise string isn't known, so any move off
    claude_team counts — and the notification quotes what it actually read."""
    _isolate(tempfile.mkdtemp())
    _write_profile("claude_team")
    sent = []
    _watch(sent)
    _write_profile("claude_enterprise")
    _watch(sent)
    assert len(sent) == 1, sent
    assert "claude_enterprise" in sent[0][1] and "Team" in sent[0][1], sent
    _watch(sent)                                  # later ticks, same value: silent
    _watch(sent)
    assert len(sent) == 1, sent


def test_plan_says_nothing_when_it_cannot_read():
    """Unreadable is not a change — and must not overwrite what was last seen, or
    the real move afterwards would slip by unannounced."""
    _isolate(tempfile.mkdtemp())
    _write_profile("claude_team")
    sent = []
    _watch(sent)
    for broken in (lambda: os.remove(m.CLAUDE_JSON),
                   lambda: open(m.CLAUDE_JSON, "w").write("{broken"),
                   lambda: json.dump({"other": 1}, open(m.CLAUDE_JSON, "w")),
                   lambda: _write_profile(None),
                   lambda: _write_profile("")):
        broken()
        assert _watch(sent) is None
    assert sent == []
    assert json.load(open(m.plan_state_path())) == {"organizationType": "claude_team"}
    _write_profile("claude_enterprise")           # …so the real move still lands
    _watch(sent)
    assert len(sent) == 1, sent


def test_plan_no_noise_except_leaving_team():
    """Returning to Team, or moving between other plans, isn't the event."""
    _isolate(tempfile.mkdtemp())
    sent = []
    for org in ("claude_max", "claude_pro", "claude_team", "claude_team"):
        _write_profile(org)
        _watch(sent)
    assert sent == [], sent
    _write_profile("claude_enterprise")           # leaving Team again is
    _watch(sent)
    assert len(sent) == 1, sent


def test_plan_survives_a_corrupt_state_file():
    _isolate(tempfile.mkdtemp())
    os.makedirs(m.APP_DIR, exist_ok=True)
    open(m.plan_state_path(), "w").write("[1, 2")
    _write_profile("claude_team")
    sent = []
    assert _watch(sent) is None and sent == []    # treated as a first run
    assert json.load(open(m.plan_state_path())) == {"organizationType": "claude_team"}


def test_notify_is_a_no_op_off_macos():
    saved = (sys.platform, m.subprocess.run)
    calls = []
    m.subprocess.run = lambda *a, **k: calls.append(a)
    sys.platform = "linux"
    try:
        assert m.notify("t", "b") is None
    finally:
        sys.platform, m.subprocess.run = saved
    assert calls == []


def test_notify_goes_through_swiftbar_by_file_name():
    """SwiftBar finds a plugin by its file name, and doesn't decode '+' as a space —
    so spaces must travel as %20 or the banner reads 'Your+org+is…'."""
    saved = (sys.platform, m.subprocess.run, m._swiftbar_present, sys.argv,
             os.environ.pop("SWIFTBAR_PLUGIN_PATH", None))
    calls = []
    m.subprocess.run = lambda cmd, **k: calls.append(cmd)
    m._swiftbar_present = lambda: True
    sys.platform = "darwin"
    sys.argv = ["/Users/x/Library/Application Support/SwiftBar/Plugins/claude-usage.5m.py"]
    try:
        assert m.notify("Claude plan changed", "now “claude_enterprise” & more") == "SwiftBar"
    finally:
        sys.platform, m.subprocess.run, m._swiftbar_present, sys.argv = saved[:4]
        if saved[4] is not None:
            os.environ["SWIFTBAR_PLUGIN_PATH"] = saved[4]
    cmd = calls[0]
    assert cmd[:2] == ["/usr/bin/open", "-g"], cmd
    url = cmd[2]
    assert url.startswith("swiftbar://notify?") and "plugin=claude-usage.5m.py" in url, url
    assert "+" not in url and "%20" in url, url
    q = urllib.parse.parse_qs(url.split("?", 1)[1])
    assert q["body"] == ["now “claude_enterprise” & more"], q     # round-trips intact


def test_notify_falls_back_to_osascript_without_swiftbar():
    saved = (sys.platform, m.subprocess.run, m._swiftbar_present)
    calls = []
    m.subprocess.run = lambda cmd, **k: calls.append(cmd)
    m._swiftbar_present = lambda: False
    sys.platform = "darwin"
    try:
        assert m.notify('say "hi"', 'quote " and \\ backslash') == "Script Editor"
    finally:
        sys.platform, m.subprocess.run, m._swiftbar_present = saved
    cmd = calls[0]
    assert cmd[0] == "/usr/bin/osascript"
    # title and body travel as argv — never spliced into the script's source
    assert cmd[-2:] == ['say "hi"', 'quote " and \\ backslash'], cmd
    assert not any('say "hi"' in part for part in cmd[:-2]), cmd


def test_nothing_about_privacy_in_the_menu():
    """No dot in the menu bar, no section in the dropdown — just usage."""
    _isolate(tempfile.mkdtemp())
    _write_profile("claude_enterprise")
    out = _render_main({"five_hour": {"utilization": 5}})
    assert _title_of(out).strip() == "5%", _title_of(out)
    for noise in ("🟢", "🟡", "🔴", "Org can", "org policy", "plan confirmed",
                  "claude_team", "claude_enterprise", "Learnyst"):
        assert noise not in out, noise


def test_main_survives_a_broken_watcher():
    _isolate(tempfile.mkdtemp())
    saved = m.watch_plan
    m.watch_plan = lambda: 1 / 0
    try:
        out = _render_main({"five_hour": {"utilization": 5}})
    finally:
        m.watch_plan = saved
    assert _title_of(out).strip() == "5%"


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
