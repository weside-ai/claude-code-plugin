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


def test_options_come_from_the_profile_and_any_marketplace(tmp_path):
    _settings(tmp_path / "p", {"we@other-market": {"options": {"autoMaterialize": True}}})
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / "p")}
    assert claude_home.plugin_option("autoMaterialize", env) is True
    assert claude_home.plugin_option("autoStoreConversations", env) is None


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
