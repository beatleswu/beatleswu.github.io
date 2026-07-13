import builtins
import types

import app as app_module


def test_premium_weekly_flag_parser_treats_false_values_as_disabled(monkeypatch):
    for value in (None, "", "0", "false", "False", "no", "off", "   "):
        if value is None:
            monkeypatch.delenv("PREMIUM_WEEKLY_SCHEDULER_ENABLED", raising=False)
        else:
            monkeypatch.setenv("PREMIUM_WEEKLY_SCHEDULER_ENABLED", value)

        assert app_module._env_flag_enabled("PREMIUM_WEEKLY_SCHEDULER_ENABLED") is False


def test_premium_weekly_flag_parser_accepts_explicit_true_values(monkeypatch):
    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("PREMIUM_WEEKLY_SCHEDULER_ENABLED", value)
        assert app_module._env_flag_enabled("PREMIUM_WEEKLY_SCHEDULER_ENABLED") is True


def test_premium_weekly_scheduler_disabled_by_default_never_imports_or_starts_thread(monkeypatch):
    original_import = builtins.__import__
    import_calls = []
    thread_calls = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        import_calls.append(name)
        if name == "premium_weekly_job":
            raise AssertionError("premium_weekly_job must not be imported when scheduler is disabled")
        return original_import(name, globals, locals, fromlist, level)

    class FakeThread:
        def __init__(self, *args, **kwargs):
            thread_calls.append((args, kwargs))

        def start(self):
            thread_calls.append(("start",))

    monkeypatch.delenv("PREMIUM_WEEKLY_SCHEDULER_ENABLED", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    app_module._start_premium_weekly_scheduler()

    assert thread_calls == []
    assert "premium_weekly_job" not in import_calls


def test_premium_weekly_scheduler_starts_only_for_explicit_true(monkeypatch):
    original_import = builtins.__import__
    imported = []
    thread_started = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        imported.append(name)
        if name == "premium_weekly_job":
            module = types.SimpleNamespace(run_once=lambda app_module: (_ for _ in ()).throw(SystemExit("stop after import")))
            return module
        return original_import(name, globals, locals, fromlist, level)

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon

        def start(self):
            thread_started.append((self.name, self.daemon, callable(self.target)))
            try:
                self.target()
            except SystemExit:
                thread_started.append(("system_exit",))

    monkeypatch.setenv("PREMIUM_WEEKLY_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    app_module._start_premium_weekly_scheduler()

    assert any(name == "premium_weekly_job" for name in imported)
    assert thread_started[0] == ("premium-weekly", True, True)
    assert thread_started[-1] == ("system_exit",)


def test_community_leaderboard_weekly_flag_parser_treats_false_values_as_disabled(monkeypatch):
    for value in (None, "", "0", "false", "False", "no", "off", "   "):
        if value is None:
            monkeypatch.delenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", raising=False)
        else:
            monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", value)

        assert app_module._env_flag_enabled("COMMUNITY_LEADERBOARD_REWARDS_ENABLED") is False


def test_community_leaderboard_weekly_flag_parser_accepts_explicit_true_values(monkeypatch):
    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", value)
        assert app_module._env_flag_enabled("COMMUNITY_LEADERBOARD_REWARDS_ENABLED") is True


def test_community_leaderboard_scheduler_disabled_by_default_never_imports_or_starts_thread(monkeypatch):
    original_import = builtins.__import__
    import_calls = []
    thread_calls = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        import_calls.append(name)
        if name == "community_leaderboard_rewards_scheduler":
            raise AssertionError("community scheduler module must not be imported when scheduler is disabled")
        return original_import(name, globals, locals, fromlist, level)

    class FakeThread:
        def __init__(self, *args, **kwargs):
            thread_calls.append((args, kwargs))

        def start(self):
            thread_calls.append(("start",))

    monkeypatch.delenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    app_module._start_community_leaderboard_weekly_scheduler()

    assert thread_calls == []
    assert "community_leaderboard_rewards_scheduler" not in import_calls


def test_community_leaderboard_scheduler_starts_only_for_explicit_true(monkeypatch):
    original_import = builtins.__import__
    imported = []
    thread_started = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        imported.append(name)
        if name == "community_leaderboard_rewards_scheduler":
            module = types.SimpleNamespace(
                SCHEDULER_WAKE_INTERVAL_SECONDS=60,
                run_community_leaderboard_weekly_cycle=lambda app_module: (_ for _ in ()).throw(SystemExit("stop after import"))
            )
            return module
        return original_import(name, globals, locals, fromlist, level)

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon

        def start(self):
            thread_started.append((self.name, self.daemon, callable(self.target)))
            try:
                self.target()
            except SystemExit:
                thread_started.append(("system_exit",))

    monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    app_module._start_community_leaderboard_weekly_scheduler()

    assert any(name == "community_leaderboard_rewards_scheduler" for name in imported)
    assert thread_started[0] == ("community-leaderboard-weekly", True, True)
    assert thread_started[-1] == ("system_exit",)
