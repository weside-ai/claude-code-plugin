#!/usr/bin/env python3
"""Where Claude Code keeps its own files, and the we plugin's options: one reader.

``config_dir()`` is Claude Code's config folder for this session: ``$CLAUDE_CONFIG_DIR`` (a pinned
session's profile, e.g. a claude-swap profile) else ``~/.claude``. Claude Code's own files live
there: ``settings.json``, ``.credentials.json`` (the MCP OAuth tokens), ``projects/`` (transcripts).

The plugin's shared state (``we-state``, ``we-timing``, ``we/news``, ``we/identity``, ``we-focus``)
stays under ``~/.claude`` on purpose: a pinned master and the unpinned sessions of the same crew
read one board, one news cursor, one identity cache. Those paths do not come from here.

``plugin_option(key)`` reads a ``userConfig`` option of the we plugin: ``CLAUDE_PLUGIN_OPTION_<KEY>``
first (Claude Code sets it for the plugin's hooks; ``false``/``0``/``no``/``off`` read as False),
else ``pluginConfigs["we@weside-ai"].options`` in ``config_dir()/settings.json``. A missing
or unreadable settings file reads as no option.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PLUGIN_ID = "we@weside-ai"
_FALSE = ("false", "0", "no", "off", "")


def config_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    value = env.get("CLAUDE_CONFIG_DIR")
    if value:
        return Path(value).expanduser()
    home = env.get("HOME")
    return (Path(home) if home else Path.home()) / ".claude"


def settings(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    try:
        with open(config_dir(env) / "settings.json", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def plugin_options(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The we plugin's options from settings.json, from the ``we@weside-ai`` entry only: a fork
    installed from another marketplace never switches an option of this one."""
    configs = settings(env).get("pluginConfigs")
    entry = configs.get(PLUGIN_ID) if isinstance(configs, dict) else None
    opts = entry.get("options") if isinstance(entry, dict) else None
    return opts if isinstance(opts, dict) else {}


def plugin_option(key: str, env: Mapping[str, str] | None = None) -> Any:
    env = os.environ if env is None else env
    raw = env.get("CLAUDE_PLUGIN_OPTION_" + key.upper())
    if raw is not None:
        if raw.strip().lower() in _FALSE:
            return False
        if raw.strip().lower() in ("true", "1", "yes", "on"):
            return True
        return raw
    return plugin_options(env).get(key)
