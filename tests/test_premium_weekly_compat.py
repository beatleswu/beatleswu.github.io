import builtins

import app as app_module


def test_premium_weekly_rating_helpers_fall_back_when_module_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "premium_weekly":
            raise ModuleNotFoundError("No module named 'premium_weekly'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    item_version, model_version, rank_to_rating = app_module._load_premium_weekly_rating_helpers()

    assert item_version == "premium-weekly-compat-missing-module"
    assert model_version == "premium-weekly-compat-missing-module"
    assert callable(rank_to_rating)
    assert rank_to_rating("3k") == app_module._RANK_TO_RATING["3k"]
