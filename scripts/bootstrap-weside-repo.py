#!/usr/bin/env python3
"""Bootstrap a `.weside/` directory in a target repo.

Generates the three Companion Framework files in one shot:

- `.weside/config.json` — technical config (council roster, meetings, stack)
- `.weside/weside.md`    — companion-facing crew + repo purpose + meetings
- `.weside/council.json` — thin bridge (role + color per slug), **gitignored**

Plus appends `.weside/council.json` to the repo's `.gitignore` (identity
text never enters a project repo; the same rule applies to the
per-companion agent files under `~/.claude/agents/`).

The script is designed to replace the interactive `/we:setup` flow when
rolling out the framework across many repos at once. It is idempotent —
existing files are preserved by default; use ``--force`` to overwrite.

Usage::

    bootstrap-weside-repo.py --repo /path/to/repo \\
                             --flavor engineering \\
                             --purpose "FastAPI backend + Expo mobile app"

Flavors: ``engineering`` | ``landing`` | ``business-docs`` | ``plugin``
| ``infrastructure`` | ``personal`` | ``mixed``.

The default crew is **generic** (role-derived names, null Companion
IDs) — public-repo-safe. To inject a real crew (with names and
Companion IDs from your weside account), pass
``--crew-from ~/.weside/crew.json`` where the JSON file has the shape
``{"crew": [{slug, name, role, color, companion_id, headline, focus}, ...]}``.
That file lives in your user scope and is never committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Crew + flavor defaults
# --------------------------------------------------------------------------- #

# Generic crew template. Public-safe — uses role-derived display names and
# null Companion IDs. Override with --crew-from <json-path> to inject a
# real crew (typically lives in user-scope ~/.weside/crew.json with the
# shape `{"crew": [...]}` mirroring the records below).
#
# Each entry's `slug` is the bridge-file key; `role` maps to the plugin's
# shipped `council-<role>` shell (or "<custom>" → unknown role, skipped
# per `we/skills/council/SKILL.md` Step 3).
DEFAULT_CREW: list[dict] = [
    {
        "slug": "orchestrator",
        "name": "Orchestrator",
        "role": "orchestrator",
        "color": "purple",
        "companion_id": None,
        "headline": "Orchestrator",
        "focus": (
            "Holds the vision, coordinates the crew, synthesises council "
            "perspectives, balances cross-domain priorities"
        ),
    },
    {
        "slug": "product-owner",
        "name": "Product Owner",
        "role": "product_owner",
        "color": "orange",
        "companion_id": None,
        "headline": "Product Owner",
        "focus": "Backlog, prioritization, AC-quality, value-ranking",
    },
    {
        "slug": "scrum-master",
        "name": "Scrum Master",
        "role": "scrum_master",
        "color": "gray",
        "companion_id": None,
        "headline": "Scrum Master",
        "focus": "Moderation, process, hand-offs, rituals — workflow clarity",
    },
    {
        "slug": "architect",
        "name": "Architect",
        "role": "architect",
        "color": "green",
        "companion_id": None,
        "headline": "Architect",
        "focus": "Target architecture, constraints, ADRs, technical coherence",
    },
    {
        "slug": "marketing",
        "name": "Marketing",
        "role": "marketing",
        "color": "blue",
        "companion_id": None,
        "headline": "Marketing",
        "focus": "Content, positioning, brand, term-claiming, messaging pipeline",
    },
    {
        "slug": "sales",
        "name": "Sales",
        "role": "sales",
        "color": "yellow",
        "companion_id": None,
        "headline": "Sales",
        "focus": "Pipeline, deals, contract drafts, customer conversations",
    },
    {
        "slug": "legal",
        "name": "Legal",
        "role": "legal",
        "color": "black",
        "companion_id": None,
        "headline": "Legal / Compliance",
        "focus": "Contracts, GDPR, AI Act, terms, compliance review",
    },
    {
        "slug": "security",
        "name": "Security",
        "role": "security",
        "color": "white",
        "companion_id": None,
        "headline": "Security / Data Protection",
        "focus": "Pen-tests, DPIAs, security reviews, hardening",
    },
]


def load_crew_override(path: str) -> list[dict]:
    """Load a real-crew override from a JSON file.

    Expected shape: ``{"crew": [<member>, ...]}`` where each member has
    the same keys as ``DEFAULT_CREW``. Companion IDs and real names are
    typically private — store the override outside any committed repo
    (recommended: ``~/.weside/crew.json``, mode 0600).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    crew = data.get("crew")
    if not isinstance(crew, list) or not crew:
        raise ValueError(f"{path}: expected non-empty 'crew' list")
    required = {"slug", "name", "role", "color", "companion_id"}
    for i, m in enumerate(crew):
        missing = required - set(m)
        if missing:
            raise ValueError(f"{path}: crew[{i}] missing keys: {sorted(missing)}")
    return crew


# Flavor profile = which meetings happen here, which default council convenes.
FLAVOR_PROFILES: dict[str, dict] = {
    "engineering": {
        "label": "Backend/Engineering",
        "council_default": ["product_owner", "architect", "scrum_master"],
        "meetings": {
            "vision": [
                "product_owner",
                "architect",
                "orchestrator",
                "marketing",
            ],
            "saga": ["product_owner", "architect", "orchestrator"],
            "epic": ["product_owner", "architect", "orchestrator"],
            "story": ["product_owner", "architect"],
        },
        "stack_default": ["python"],
    },
    "landing": {
        "label": "Landing/Marketing",
        "council_default": ["product_owner", "marketing", "ux_researcher"],
        "meetings": {
            "vision": ["product_owner", "marketing", "orchestrator"],
            "saga": ["product_owner", "marketing", "orchestrator"],
            "epic": ["product_owner", "marketing", "orchestrator"],
            "story": ["product_owner", "marketing"],
        },
        "stack_default": ["typescript"],
    },
    "business-docs": {
        "label": "Business docs / Strategy",
        "council_default": ["orchestrator", "product_owner", "marketing"],
        "meetings": {
            "vision": [
                "orchestrator",
                "product_owner",
                "marketing",
                "sales",
                "legal",
            ],
            "saga": ["product_owner", "architect", "orchestrator"],
            "epic": ["product_owner", "architect", "orchestrator"],
            "story": ["product_owner", "architect"],
        },
        "stack_default": ["markdown-only"],
    },
    "plugin": {
        "label": "Plugin / toolkit",
        "council_default": ["product_owner", "architect", "scrum_master"],
        "meetings": {
            "vision": [
                "product_owner",
                "architect",
                "ux_researcher",
                "orchestrator",
            ],
            "saga": ["product_owner", "architect", "orchestrator"],
            "epic": ["product_owner", "architect", "orchestrator"],
            "story": ["product_owner", "architect"],
        },
        "stack_default": ["typescript", "markdown"],
    },
    "infrastructure": {
        "label": "Infrastructure / DevOps",
        "council_default": ["architect", "security", "scrum_master"],
        "meetings": {
            "vision": ["architect", "security", "orchestrator"],
            "saga": ["architect", "security", "orchestrator"],
            "epic": ["architect", "security", "orchestrator"],
            "story": ["architect", "security"],
        },
        "stack_default": ["terraform", "yaml"],
    },
    "personal": {
        "label": "Personal / Private",
        "council_default": ["orchestrator"],
        "meetings": {
            "vision": ["orchestrator"],
            "saga": ["orchestrator"],
            "epic": ["orchestrator"],
            "story": ["orchestrator"],
        },
        "stack_default": ["markdown-only"],
    },
    "mixed": {
        "label": "Mixed / Custom",
        "council_default": ["product_owner", "architect", "scrum_master"],
        "meetings": {
            "vision": [
                "product_owner",
                "architect",
                "ux_researcher",
                "marketing",
                "orchestrator",
            ],
            "saga": ["product_owner", "architect", "orchestrator"],
            "epic": ["product_owner", "architect", "orchestrator"],
            "story": ["product_owner", "architect"],
        },
        "stack_default": [],
    },
}

GITIGNORE_MARKER = "# Companion Framework — bridge file holds crew membership"
GITIGNORE_PATH_LINE = ".weside/council.json"


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def render_config_json(
    *,
    vault: str,
    flavor: str,
    profile: dict,
    purpose: str,
    stack: list[str],
    ticketing_tool: str,
    ticketing_project_key: str | None,
    cross_repo: dict | None,
    crew: list[dict],
) -> dict:
    """Build the `.weside/config.json` payload."""
    roles_enabled = sorted({m["role"] for m in crew})
    return {
        "vault": vault,
        "framework_version": 1,
        "onboarded": True,
        "onboarded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "repo_flavor": flavor,
        "roles_enabled": roles_enabled,
        "ticketing": {
            "tool": ticketing_tool,
            "project_key": ticketing_project_key,
            "note": (
                f"Repo flavor: {profile['label']}. "
                f"Stack: {', '.join(stack) if stack else 'unspecified'}."
            ),
        },
        "stack": stack,
        "council": {
            "default": profile["council_default"],
            "meetings": profile["meetings"],
        },
        **({"cross_repo": cross_repo} if cross_repo else {}),
    }


def render_council_json(crew: list[dict]) -> dict:
    """Build the **thin** `.weside/council.json` bridge payload.

    Thin schema: role + color + display-name per slug. No identity_prompt —
    identity is now served by the `get_council` MCP method. The bridge
    remains for role/color/membership only.
    """
    return {
        "version": 2,
        "schema": "thin",
        "workspace_id": None,
        "members": {
            m["slug"]: {
                "name": m["name"],
                "role": m["role"],
                "color": m["color"],
                "companion_id": m["companion_id"],
            }
            for m in crew
        },
    }


def render_weside_md(
    *,
    repo_name: str,
    vault: str,
    purpose: str,
    profile: dict,
    crew: list[dict],
    cross_repo_block: str,
    notes: str,
    stakeholder: str | None = None,
) -> str:
    """Build the `.weside/weside.md` document."""
    lines: list[str] = []
    lines.append("---")
    lines.append("type: weside")
    lines.append("version: 1")
    lines.append(f"repo: {repo_name}")
    lines.append(f"vault: {vault}")
    if stakeholder:
        lines.append(f"stakeholder: {stakeholder}")
    lines.append("---")
    lines.append("")
    lines.append(f"# weside — {repo_name}")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append(purpose.strip())
    lines.append("")
    lines.append("## Crew")
    lines.append("")
    for m in crew:
        lines.append(f"### {m['name']} — {m['headline']}")
        lines.append("")
        lines.append(f"- **Companion ID:** {m['companion_id']}")
        lines.append(f"- **Role(s):** `{m['role']}`")
        lines.append(f"- **Color:** {m['color']}")
        lines.append(f"- **Focus:** {m['focus']}")
        in_meetings = [
            meeting for meeting, roster in profile["meetings"].items() if m["role"] in roster
        ]
        lines.append(
            "- **In meetings:** "
            + (", ".join(in_meetings) if in_meetings else "(none configured)")
        )
        lines.append("")

    lines.append("## Meetings held here")
    lines.append("")
    for meeting, roster in profile["meetings"].items():
        names = []
        for role in roster:
            for m in crew:
                if m["role"] == role:
                    names.append(m["name"])
                    break
        lines.append(
            f"- **{meeting}** — roster: {', '.join(names) if names else '(roster empty)'}"
        )
    lines.append("")

    lines.append("## Cross-repo relations")
    lines.append("")
    lines.append(cross_repo_block.strip() or "(none)")
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append(notes.strip() or "(none)")
    lines.append("")

    lines.append("## Companion identity")
    lines.append("")
    lines.append(
        "Personalities, memories, body, and voice live in weside (the MCP "
        "backend). This file references companions by name + `Companion ID` "
        "only. Identity bodies are fetched at runtime via "
        "`mcp__plugin_we_weside-mcp__get_council` (preferred) or the thin "
        "`.weside/council.json` bridge (fallback). The bridge is gitignored — "
        "identity text never enters a project repo verbatim."
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #


def merge_config(existing: dict, new: dict) -> dict:
    """Merge new config into existing, preserving fields the new payload
    doesn't set (notably any user-edited council overrides)."""
    out = dict(existing)
    for key, value in new.items():
        if key == "council" and isinstance(existing.get("council"), dict):
            # Preserve existing council customizations; only add missing.
            merged_council = dict(existing["council"])
            for ck, cv in value.items():
                merged_council.setdefault(ck, cv)
            out["council"] = merged_council
        elif key == "cross_repo" and isinstance(existing.get("cross_repo"), dict):
            # Don't overwrite cross-repo manually configured by humans.
            continue
        elif key == "onboarded_at" and existing.get("onboarded_at"):
            # Preserve the original onboarded-at timestamp.
            continue
        else:
            out[key] = value
    return out


def ensure_gitignore(repo_path: Path) -> bool:
    """Append `.weside/council.json` to `.gitignore` if not already present.

    Returns True if the file was modified.
    """
    gi = repo_path / ".gitignore"
    if not gi.exists():
        gi.write_text(f"{GITIGNORE_MARKER}\n{GITIGNORE_PATH_LINE}\n", encoding="utf-8")
        return True
    content = gi.read_text(encoding="utf-8")
    if GITIGNORE_PATH_LINE in content.splitlines():
        return False
    sep = "" if content.endswith("\n") else "\n"
    gi.write_text(
        content + f"{sep}\n{GITIGNORE_MARKER}\n{GITIGNORE_PATH_LINE}\n",
        encoding="utf-8",
    )
    return True


def write_files(
    *,
    repo_path: Path,
    config: dict,
    council: dict,
    weside_md: str,
    force: bool,
) -> dict[str, str]:
    """Write the three files. Returns a {file: status} report."""
    weside_dir = repo_path / ".weside"
    weside_dir.mkdir(exist_ok=True)
    report: dict[str, str] = {}

    cfg_path = weside_dir / "config.json"
    if cfg_path.exists() and not force:
        existing = json.loads(cfg_path.read_text(encoding="utf-8"))
        merged = merge_config(existing, config)
        cfg_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        report["config.json"] = "merged"
    else:
        cfg_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        report["config.json"] = "written"

    md_path = weside_dir / "weside.md"
    if md_path.exists() and not force:
        report["weside.md"] = "kept (use --force to overwrite)"
    else:
        md_path.write_text(weside_md, encoding="utf-8")
        report["weside.md"] = "written"

    council_path = weside_dir / "council.json"
    if council_path.exists() and not force:
        # Check if existing is fat (legacy) or thin (new). Migrate fat → thin.
        existing = json.loads(council_path.read_text(encoding="utf-8"))
        is_fat = any("identity_prompt" in m for m in existing.get("members", {}).values())
        if is_fat:
            council_path.write_text(json.dumps(council, indent=2) + "\n", encoding="utf-8")
            report["council.json"] = "shrunk (fat → thin schema)"
        else:
            report["council.json"] = "kept (already thin)"
    else:
        council_path.write_text(json.dumps(council, indent=2) + "\n", encoding="utf-8")
        report["council.json"] = "written"

    if ensure_gitignore(repo_path):
        report[".gitignore"] = "updated"
    else:
        report[".gitignore"] = "already covers .weside/council.json"

    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", required=True, help="Absolute path to the target repo root")
    parser.add_argument(
        "--flavor",
        required=True,
        choices=list(FLAVOR_PROFILES.keys()),
        help="Repo flavor — drives default council + meeting roster",
    )
    parser.add_argument(
        "--purpose",
        required=True,
        help="Purpose section content (1-3 sentences, plain text)",
    )
    parser.add_argument(
        "--vault",
        default=None,
        help="TurboVault name (default: repo basename)",
    )
    parser.add_argument(
        "--ticketing-tool",
        default="none",
        choices=["jira", "github-issues", "none"],
    )
    parser.add_argument(
        "--ticketing-project-key",
        default=None,
        help="Jira project key, e.g. 'WA' — only used with --ticketing-tool=jira",
    )
    parser.add_argument(
        "--stack",
        default=None,
        help="Comma-separated stack list (e.g. 'python,typescript'). "
        "If omitted, the flavor's stack_default is used.",
    )
    parser.add_argument(
        "--cross-repo",
        default="(none)",
        help="Plain-text Cross-repo block for weside.md. Use multi-line "
        "via shell heredoc if needed.",
    )
    parser.add_argument(
        "--notes",
        default="(none)",
        help="Plain-text Notes block for weside.md.",
    )
    parser.add_argument(
        "--stakeholder",
        default=None,
        help="Name of the human stakeholder for this repo. Omitted from "
        "the weside.md frontmatter when not provided (public-safe default).",
    )
    parser.add_argument(
        "--crew-from",
        default=None,
        help="Path to a JSON file with the real crew (shape: "
        "{'crew': [{slug, name, role, color, companion_id, headline, focus}, ...]}). "
        "Recommended location: ~/.weside/crew.json (user-scope, never committed). "
        "Without this flag, generic public-safe defaults are used.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite weside.md if it exists (config.json always merges, "
        "council.json always migrates fat to thin)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written; don't touch the filesystem.",
    )

    args = parser.parse_args()

    repo_path = Path(args.repo).expanduser().resolve()
    if not repo_path.is_dir():
        print(f"error: --repo {repo_path} is not a directory", file=sys.stderr)
        return 2

    repo_name = repo_path.name
    vault = args.vault or repo_name
    profile = FLAVOR_PROFILES[args.flavor]
    stack = [s.strip() for s in args.stack.split(",")] if args.stack else profile["stack_default"]

    crew = list(DEFAULT_CREW)
    if args.crew_from:
        crew_path = Path(args.crew_from).expanduser().resolve()
        if not crew_path.is_file():
            print(f"error: --crew-from {crew_path} not found", file=sys.stderr)
            return 2
        try:
            crew = load_crew_override(str(crew_path))
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            print(f"error: --crew-from {crew_path}: {exc}", file=sys.stderr)
            return 2
        print(f"# crew loaded from {crew_path} ({len(crew)} members)")

    config = render_config_json(
        vault=vault,
        flavor=args.flavor,
        profile=profile,
        purpose=args.purpose,
        stack=stack,
        ticketing_tool=args.ticketing_tool,
        ticketing_project_key=args.ticketing_project_key,
        cross_repo=None,
        crew=crew,
    )
    council = render_council_json(crew)
    weside_md = render_weside_md(
        repo_name=repo_name,
        vault=vault,
        purpose=args.purpose,
        profile=profile,
        crew=crew,
        cross_repo_block=args.cross_repo,
        notes=args.notes,
        stakeholder=args.stakeholder,
    )

    if args.dry_run:
        print(f"# Dry run for {repo_path}\n")
        print("## .weside/config.json")
        print(json.dumps(config, indent=2))
        print("\n## .weside/weside.md")
        print(weside_md)
        print("\n## .weside/council.json")
        print(json.dumps(council, indent=2))
        print(f"\n## .gitignore\n# would append: {GITIGNORE_PATH_LINE}")
        return 0

    report = write_files(
        repo_path=repo_path,
        config=config,
        council=council,
        weside_md=weside_md,
        force=args.force,
    )

    print(f"Bootstrapped .weside/ in {repo_path}")
    for f, status in report.items():
        print(f"  {f:18s} {status}")
    print(
        "\nNext: review the generated files, commit the .weside/{config.json,"
        "weside.md} pair (council.json is gitignored)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
