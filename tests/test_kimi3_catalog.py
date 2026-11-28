"""Regression coverage for broker catalog admission and Kimi alias ownership."""

from scripts.refresh_broker_catalogs import CHAT, compile_catalogs


def ci_row(name, owner):
    return {
        "id": name,
        "owned_by": owner,
        "type": "text",
        "supported_endpoints": [CHAT],
        "context_length": 1000,
        "max_output_tokens": 100,
        "supported_parameters": {CHAT: ["tools"]},
        "capabilities": {"vision": False},
    }


def router_row(wire):
    return {
        "id": wire,
        "context_length": 1000,
        "top_provider": {"max_completion_tokens": 100},
        "supported_parameters": ["tools"],
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    }


def test_kimi3_admission_preserves_legacy_aliases_and_excludes_other_new_models():
    families = [("gpt-test", "openai"), ("gemini-test", "google"), ("claude-test", "anthropic"), ("grok-test", "xai")]
    ci = [ci_row(name, owner) for name, owner in families]
    ci += [
        ci_row(name, "Moonshot")
        for name in ("kimi-k2.6", "kimi-k2.5", "kimi-k2", "kimi-k3", "kimi-k3-fast", "kimi-k3.1-pro", "kimi-k3-batch")
    ]
    router = [
        router_row(f"{namespace}/{name}")
        for (name, _), namespace in zip(families, ("openai", "google", "anthropic", "x-ai"))
    ]
    router += [
        router_row(f"moonshotai/{name}")
        for name in ("kimi-k2.6", "kimi-k2.5", "kimi-k2", "kimi-k3", "kimi-k3-fast", "kimi-k3.1-pro", "kimi-k3:batch")
    ]

    first = compile_catalogs(ci, router)
    assert first == compile_catalogs(ci, router)
    for entries, prefix in zip(first, ("", "moonshotai/")):
        by_name = {entry["model_name"]: entry for entry in entries}
        assert {prefix + name for name in ("kimi-k3", "kimi-k3-fast", "kimi-k3.1-pro")} <= by_name.keys()
        assert prefix + "kimi-k2" not in by_name
        assert prefix + "kimi-k3-batch" not in by_name
        assert prefix + "kimi-k3:batch" not in by_name
        assert {"kimi", "kimi-k2"} <= set(by_name[prefix + "kimi-k2.6"]["aliases"])
        assert all(
            by_name[prefix + name]["context_window"] > 0 and by_name[prefix + name]["max_output_tokens"] > 0
            for name in ("kimi-k3", "kimi-k3-fast", "kimi-k3.1-pro")
        )


def test_additive_cli_preserves_baseline_and_adds_only_prefix(tmp_path, monkeypatch):
    import json
    import sys

    import scripts.refresh_broker_catalogs as refresh

    baseline = [{"model_name": "existing", "aliases": ["old"], "context_window": 123}]
    generated = [
        {"model_name": "existing", "aliases": ["changed"], "context_window": 999},
        {"model_name": "kimi-k3", "aliases": ["moonshotai/kimi-k3"]},
        {"model_name": "unrelated", "aliases": []},
    ]
    for filename in ("cheaperinference_models.json", "openrouter_chat_models.json"):
        (tmp_path / filename).write_text(json.dumps({"models": baseline}))
    monkeypatch.setattr(refresh, "rows", lambda path: [path])
    monkeypatch.setattr(refresh, "compile_catalogs", lambda *_: (generated, generated))
    monkeypatch.setattr(
        sys,
        "argv",
        ["refresh", "ci.json", "router.json", "--output-dir", str(tmp_path), "--add-only-prefix", "kimi-k3"],
    )
    refresh.main()
    for filename in ("cheaperinference_models.json", "openrouter_chat_models.json"):
        assert json.loads((tmp_path / filename).read_text())["models"] == [baseline[0], generated[1]]


def test_additive_cli_rejects_empty_prefix_missing_baseline_and_alias_collision(tmp_path, monkeypatch):
    import json
    import sys

    import pytest

    import scripts.refresh_broker_catalogs as refresh

    monkeypatch.setattr(refresh, "rows", lambda path: [path])
    generated = [{"model_name": "kimi-k3", "aliases": ["shared"]}]
    monkeypatch.setattr(refresh, "compile_catalogs", lambda *_: (generated, generated))
    args = ["refresh", "ci.json", "router.json", "--output-dir", str(tmp_path), "--add-only-prefix"]
    monkeypatch.setattr(sys, "argv", args + [""])
    with pytest.raises((ValueError, SystemExit)):
        refresh.main()
    monkeypatch.setattr(sys, "argv", args + ["kimi-k3"])
    with pytest.raises((ValueError, FileNotFoundError)):
        refresh.main()
    baseline = {"models": [{"model_name": "existing", "aliases": ["shared"]}]}
    for filename in ("cheaperinference_models.json", "openrouter_chat_models.json"):
        (tmp_path / filename).write_text(json.dumps(baseline))
    with pytest.raises(ValueError, match="alias"):
        refresh.main()
    for filename in ("cheaperinference_models.json", "openrouter_chat_models.json"):
        assert json.loads((tmp_path / filename).read_text()) == baseline
