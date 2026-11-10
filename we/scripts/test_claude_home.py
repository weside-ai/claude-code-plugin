"""claude_home: Claude Code's config folder and the we plugin's options."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import claude_home


def test_config_dir_follows_claude_config_dir(tmp_path):
    assert claude_home.config_dir({"CLAUDE_CONFIG_DIR": str(tmp_path / "p")}) == tmp_path / "p"
    assert claude_home.config_dir({"HOME": str(tmp_path)}) == tmp_path / ".claude"


def _settings(folder: Path, configs: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "settings.json").write_text(json.dumps({"pluginConfigs": configs}))


def test_options_come_from_the_profile_and_the_weside_ai_entry(tmp_path):
    _settings(tmp_path / "p", {"we@weside-ai": {"options": {"autoMaterialize": True}}})
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / "p")}
    assert claude_home.plugin_option("autoMaterialize", env) is True
    assert claude_home.plugin_option("autoStoreConversations", env) is None


def test_a_we_plugin_from_another_marketplace_sets_no_option(tmp_path):
    """T2 panel on #197: a fork installed as we@<other> must not switch autoStoreConversations
    (which sends turns to the weside backend) on for the weside-ai plugin."""
    _settings(
        tmp_path / "p",
        {
            "we@another-market": {"options": {"autoStoreConversations": True}},
            "we@weside-ai": {"options": {"autoStoreConversations": False}},
        },
    )
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / "p")}
    assert claude_home.plugin_option("autoStoreConversations", env) is False
    _settings(tmp_path / "q", {"we@another-market": {"options": {"autoMaterialize": True}}})
    assert claude_home.plugin_options({"CLAUDE_CONFIG_DIR": str(tmp_path / "q")}) == {}


def test_the_plugin_option_env_wins(tmp_path):
    _settings(tmp_path / "p", {"we@weside-ai": {"options": {"autoMaterialize": True}}})
    env = {
        "CLAUDE_CONFIG_DIR": str(tmp_path / "p"),
        "CLAUDE_PLUGIN_OPTION_AUTOMATERIALIZE": "false",
    }
    assert claude_home.plugin_option("autoMaterialize", env) is False
    env["CLAUDE_PLUGIN_OPTION_AUTOMATERIALIZE"] = "true"
    assert claude_home.plugin_option("autoMaterialize", env) is True


def test_an_unreadable_settings_file_is_no_option(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "settings.json").write_text("{broken")
    assert claude_home.plugin_options({"CLAUDE_CONFIG_DIR": str(tmp_path / "p")}) == {}


def test_tmux_attention_keeps_the_same_option_rule(tmp_path, monkeypatch):
    """tmux_attention carries its own copy (it runs on every tool call); both read the same file."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
    import tmux_attention  # noqa: PLC0415

    for configs in (
        {"we@other": {"options": {"tmuxAttention": False}}},
        {"we@weside-ai": {"options": {"x": 1}}, "zz@m": {"options": {"x": 2}}},
        {"other@m": {"options": {"x": 3}}},
    ):
        _settings(tmp_path / "p", configs)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "p"))
        assert tmux_attention.plugin_options() == claude_home.plugin_options()
