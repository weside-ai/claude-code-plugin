#!/usr/bin/env python3
"""Budget gate for a repo's Claude Code instruction layer.

Checks rules (`.claude/rules/**`), skills (`**/SKILL.md` and their reference files),
subagent definitions (`agents/*.md`) and `AGENTS.md` / `CLAUDE.md` against the limits
in Claude Code's and the Agent Skills docs; the sources and the reasoning per limit live
in `references/instruction-authoring.md`. Errors exit 1, warnings print and exit 0.

Limits and excludes are overridable in `.weside/config.json`:

    {"optimization": {"budget": {"rule_lines": 200, ...}, "exclude": ["content"]}}

Warning `ref-path-missing`: a backticked repo path (it has a `/`; no glob, no `<placeholder>`, no
`{var}`, no `~/` or absolute path, both machine-bound) or a `/<plugin>:<skill>` command of a
plugin in this repo, named in an instruction file, that does not exist. A path counts when it
exists from the repo root, from the file's directory, or as the tail of a repo path. Inside a plugin only plugin paths
(`${CLAUDE_PLUGIN_ROOT}/…` or a top-level plugin directory) are checked: the rest names the
consumer repo. A line carrying `<!-- ref-ok -->` is exempt.

Usage: check-instruction-budget.py [--root DIR] [--json]
PyYAML is optional: without it the strict-YAML checks are skipped and say so.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only where PyYAML is absent
    yaml = None

DEFAULT_BUDGET = {
    "rule_lines": 200,  # memory.md: target under 200 lines per instruction file
    "rules_total_lines": 600,  # per-repo budget for unconditional rules
    "instruction_file_lines": 200,  # memory.md: AGENTS.md / CLAUDE.md
    "skill_lines": 500,  # skills.md: keep SKILL.md under 500 lines
    "skill_listing_chars": 1536,  # skills.md: description + when_to_use cap
    "agent_description_tokens": 15000,  # sub-agents.md: combined description warning
    "contents_threshold": 100,  # skill best practices: ToC for files over 100 lines
}
SKIP_PREFIXES = (".claude/worktrees/",)
INSTRUCTION_FILES = {"AGENTS.md", "CLAUDE.md", "CLAUDE.local.md"}
CONTENTS_RE = re.compile(r"^#{2,3} +(contents|table of contents)\b", re.IGNORECASE | re.MULTILINE)
LINK_RE = re.compile(r"\]\(([^)#\s]+\.md)\)|`([^`\s]+\.md)`")


sys.path.insert(0, str(Path(__file__).resolve().parent))

import rule_loading  # noqa: E402 - the sibling module, found via the line above


@dataclass(frozen=True)
class Finding:
    severity: str  # error | warning
    check: str
    path: str
    message: str


@dataclass
class Repo:
    root: Path
    budget: dict
    exclude: list[str]
    files: list[str] = field(default_factory=list)  # every repo file, for `paths:` matching
    findings: list[Finding] = field(default_factory=list)

    def error(self, check: str, path: str, message: str) -> None:
        self.findings.append(Finding("error", check, path, message))

    def warn(self, check: str, path: str, message: str) -> None:
        self.findings.append(Finding("warning", check, path, message))

    def excluded(self, rel: str) -> bool:
        parts = rel.split("/")
        if rule_loading.SKIP_DIRS.intersection(parts[:-1]) or rel.startswith(SKIP_PREFIXES):
            return True
        return any(
            item in parts[:-1] or rel.startswith(item.rstrip("/") + "/") for item in self.exclude
        )

    def instruction_paths(self, predicate) -> list[str]:
        return sorted(rel for rel in self.files if predicate(rel) and not self.excluded(rel))

    def text(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8", errors="replace")


def load_config(root: Path) -> tuple[dict, list[str]]:
    budget = dict(DEFAULT_BUDGET)
    exclude: list[str] = []
    config = root / ".weside" / "config.json"
    if config.exists():
        section = json.loads(config.read_text(encoding="utf-8")).get("optimization") or {}
        budget.update(section.get("budget") or {})
        exclude = list(section.get("exclude") or [])
    return budget, exclude


def line_count(text: str) -> int:
    return len(text.splitlines())


def strict_yaml_error(block: str) -> str | None:
    if yaml is None:
        return None
    try:
        yaml.safe_load(block)
    except yaml.YAMLError as exc:
        return str(exc).splitlines()[0]
    return None


def instruction_texts(repo: Repo) -> dict[str, str]:
    sources = repo.instruction_paths(
        lambda rel: (
            (
                rel.startswith(".claude/rules/")
                or rel.rsplit("/", 1)[-1] in INSTRUCTION_FILES
                or rel.endswith("SKILL.md")
            )
            and rel.endswith(".md")
        )
    )
    return {rel: repo.text(rel) for rel in sources}


def pointed_at(rel: str, texts: dict[str, str]) -> bool:
    """Another instruction file names this rule by its path: `.claude/rules/<key>`, or `<key>`
    not preceded by another path segment (`docs/core/x.md` does not point at `core/x.md`)."""
    key = re.escape(rel.removeprefix(".claude/rules/"))
    pattern = re.compile(rf"(?:(?<=\.claude/rules/)|(?<![\w./-])){key}(?![\w-])")
    return any(pattern.search(text) for other, text in texts.items() if other != rel)


def check_rules(repo: Repo) -> None:
    rules = repo.instruction_paths(
        lambda rel: rel.startswith(".claude/rules/") and rel.endswith(".md")
    )
    texts = instruction_texts(repo)
    unconditional_total = 0
    for rel in rules:
        text = repo.text(rel)
        block = rule_loading.frontmatter_block(text)
        rule = rule_loading.parse_rule(text, repo.root / rel)
        if rule.unconditional or (rule.defect or "").startswith("unterminated"):
            repo.error("rule-yaml", rel, str(rule.defect))
        elif block is not None and (err := strict_yaml_error(block)):
            repo.warn(
                "rule-yaml",
                rel,
                f"frontmatter is not valid YAML ({err}); Claude Code quotes the values and retries"
                " — quote them yourself",
            )
        if block is not None and re.search(r"^globs\s*:", block, re.MULTILINE):
            repo.error("rule-globs", rel, "`globs:` is ignored by Claude Code — use `paths:`")
        lines = line_count(text)
        if rule.is_always_on:
            unconditional_total += lines
            if lines > repo.budget["rule_lines"]:
                repo.error(
                    "rule-lines",
                    rel,
                    f"{lines} lines, unconditional rule max {repo.budget['rule_lines']} — add `paths:` or move detail to a skill",
                )
        else:
            check_paths_match(repo, rel, rule.patterns)
        if (
            lines > repo.budget["contents_threshold"]
            and pointed_at(rel, texts)
            and not CONTENTS_RE.search(text)
        ):
            repo.error(
                "contents-missing",
                rel,
                f"{lines} lines and pointed at by another instruction file, but no `## Contents`",
            )
    if unconditional_total > repo.budget["rules_total_lines"]:
        repo.error(
            "rules-total",
            ".claude/rules",
            f"unconditional rules total {unconditional_total} lines > budget {repo.budget['rules_total_lines']}",
        )


def check_paths_match(repo: Repo, rel: str, patterns: tuple[str, ...]) -> None:
    dead = [
        p
        for p in patterns
        if not any(rule_loading.pattern_matches(p, f, patterns) for f in repo.files)
    ]
    if dead and len(dead) == len(patterns):
        repo.error(
            "rule-paths-unmatched",
            rel,
            f"no file matches any `paths:` glob ({', '.join(dead)}) — the rule never loads",
        )
    elif dead:
        repo.warn("rule-paths-unmatched", rel, f"`paths:` glob matches no file: {', '.join(dead)}")


def check_instruction_files(repo: Repo) -> None:
    limit = repo.budget["instruction_file_lines"]
    for rel in repo.instruction_paths(lambda r: r.rsplit("/", 1)[-1] in INSTRUCTION_FILES):
        lines = line_count(repo.text(rel))
        if lines > limit:
            repo.error(
                "instruction-file-lines",
                rel,
                f"{lines} lines > {limit} — move part-of-the-codebase detail into path-scoped rules",
            )


def lenient_fields(block: str) -> dict[str, str]:
    """Claude Code's own lenient reading: `key: value` plus folded continuation lines."""
    fields: dict[str, str] = {}
    current = None
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if match:
            current = match.group(1)
            fields[current] = match.group(2).strip().lstrip(">|").strip().strip("\"'")
        elif current and line.startswith((" ", "\t")):
            fields[current] = f"{fields[current]} {line.strip()}".strip()
    return fields


def check_skills(repo: Repo) -> None:
    for rel in repo.instruction_paths(lambda r: r.endswith("SKILL.md")):
        text = repo.text(rel)
        block = rule_loading.frontmatter_block(text) or ""
        if block and (err := strict_yaml_error(block)):
            repo.warn(
                "skill-yaml",
                rel,
                f"strict YAML fails ({err}); Claude Code parses leniently and still loads it",
            )
        lines = line_count(text)
        if lines > repo.budget["skill_lines"]:
            repo.error(
                "skill-lines",
                rel,
                f"{lines} lines > {repo.budget['skill_lines']} — move detail into reference files",
            )
        fields = lenient_fields(block)
        listing = fields.get("description", "") + fields.get("when_to_use", "")
        if not fields.get("description"):
            repo.warn(
                "skill-description",
                rel,
                "no `description` — Claude Code falls back to the first body line",
            )
        elif len(listing) > repo.budget["skill_listing_chars"]:
            repo.error(
                "skill-listing",
                rel,
                f"description + when_to_use {len(listing)} chars > {repo.budget['skill_listing_chars']}",
            )
        check_skill_references(repo, rel, text)


def linked_files(repo: Repo, rel: str, text: str) -> set[str]:
    """Repo-relative `.md` files a file points at, by link or code span."""
    base = Path(rel).parent
    plugin_root = next(
        (p for p in [base, *base.parents] if (repo.root / p / ".claude-plugin").is_dir()), None
    )
    found = set()
    for match in LINK_RE.finditer(text):
        target = match.group(1) or match.group(2)
        if target.startswith("${CLAUDE_PLUGIN_ROOT}/") and plugin_root is not None:
            candidate = plugin_root / target.removeprefix("${CLAUDE_PLUGIN_ROOT}/")
        else:
            candidate = base / target
        resolved = os.path.normpath(candidate.as_posix())
        if (repo.root / resolved).is_file():
            found.add(Path(resolved).as_posix())
    return found


def is_reference_file(repo: Repo, skill_dir: str, ref: str) -> bool:
    """Inside the skill's directory, or in the shared `references/` of its plugin."""
    if ref.startswith(skill_dir + "/"):
        return True
    parent = Path(ref).parent
    return parent.name == "references" and (repo.root / parent.parent / ".claude-plugin").is_dir()


def check_skill_references(repo: Repo, rel: str, text: str) -> None:
    skill_dir = Path(rel).parent.as_posix()
    direct = linked_files(repo, rel, text) - {rel}
    for ref in sorted(r for r in direct if is_reference_file(repo, skill_dir, r)):
        ref_text = repo.text(ref)
        lines = line_count(ref_text)
        flagged = any(f.check == "contents-missing" and f.path == ref for f in repo.findings)
        if (
            lines > repo.budget["contents_threshold"]
            and not flagged
            and not CONTENTS_RE.search(ref_text)
        ):
            repo.error(
                "contents-missing", ref, f"{lines} lines, read by {rel}, but no `## Contents`"
            )
        if not ref.startswith(skill_dir + "/"):
            continue
        for nested in sorted(linked_files(repo, ref, ref_text) - direct - {rel, ref}):
            if nested.startswith(skill_dir + "/"):
                repo.error(
                    "skill-nested-ref",
                    nested,
                    f"reached only through {ref} — link it from {rel} (references stay one level deep)",
                )


def is_agent_definition(repo: Repo):
    """`.claude/agents/*.md`, or `agents/*.md` next to a plugin's `.claude-plugin/`."""

    def predicate(rel: str) -> bool:
        parts = rel.split("/")
        if len(parts) < 2 or parts[-2] != "agents" or not rel.endswith(".md"):
            return False
        parent = "/".join(parts[:-2])
        return parent.endswith(".claude") or (repo.root / parent / ".claude-plugin").is_dir()

    return predicate


def check_agents(repo: Repo) -> None:
    total_chars = 0
    agents = repo.instruction_paths(is_agent_definition(repo))
    for rel in agents:
        fields = lenient_fields(rule_loading.frontmatter_block(repo.text(rel)) or "")
        if not fields.get("name") or not fields.get("description"):
            repo.error(
                "agent-frontmatter", rel, "a subagent definition needs `name` and `description`"
            )
            continue
        total_chars += len(fields["description"])
    tokens = total_chars // 4
    if tokens > repo.budget["agent_description_tokens"]:
        repo.error(
            "agent-descriptions",
            "agents",
            f"combined subagent descriptions ~{tokens} tokens > {repo.budget['agent_description_tokens']}",
        )


CODE_SPAN_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
COMMAND_RE = re.compile(r"^/([a-z0-9-]+):([a-z0-9-]+)$")
_NOT_A_PATH = re.compile(
    r"[\s<>*?{}\[\]$|=@'\"\\…]|://|^-|^~|^/|^\.\.?$|^(origin|upstream|refs|\.git|info)/"
)
# A path names a directory (`dir/`) or a file with an extension; `ops/pod-0`, `a/b-rule`, a MIME
# type or a rate (`10/minute`) is no path.
_PATH_SHAPE = re.compile(r"(/|\.[A-Za-z0-9]{1,5})$")


def _plugin_root(repo: Repo, rel: str) -> Path | None:
    base = Path(rel).parent
    return next(
        (p for p in [base, *base.parents] if (repo.root / p / ".claude-plugin").is_dir()), None
    )


def _plugin_names(repo: Repo) -> dict[str, Path]:
    names = {}
    for rel in repo.files:
        if rel.endswith(".claude-plugin/plugin.json"):
            try:
                name = json.loads(repo.text(rel)).get("name")
            except ValueError:
                continue
            if name:
                names[name] = Path(rel).parent.parent
    return names


def _exists(repo: Repo, candidate: str, known: set[str]) -> bool:
    norm = os.path.normpath(candidate).removeprefix("./")
    return (repo.root / norm).exists() or norm in known


def _repo_candidates(repo: Repo, here: Path, token: str) -> list[str] | None:
    first = token.split("/", 1)[0]
    if (repo.root.parent / first).is_dir() and not (repo.root / first).exists():
        # A sibling repo of the workspace (`other-repo/docs/x.md`): checked there when present.
        return None if (repo.root.parent / token).exists() else [token]
    return [token, (here / token).as_posix()]


def _ref_candidates(repo: Repo, rel: str, token: str) -> list[str] | None:
    """Repo-relative paths any of which makes `token` exist; None when `token` is not checked."""
    plugin = _plugin_root(repo, rel)
    here = Path(rel).parent
    if token.startswith("${CLAUDE_PLUGIN_ROOT}/"):
        token = token.split(maxsplit=1)[0].removeprefix("${CLAUDE_PLUGIN_ROOT}/")
        return None if plugin is None else [(plugin / token).as_posix()]
    if "/" not in token or _NOT_A_PATH.search(token):
        return None
    token = re.sub(r"(::.*|:\d+(-\d+)?|#.*)$", "", token).rstrip(".,;:")
    if not _PATH_SHAPE.search(token):
        return None
    if plugin is None:
        return _repo_candidates(repo, here, token)
    first = token.split("/", 1)[0]
    if first.startswith(".") or not (
        (repo.root / plugin / first).is_dir() or (repo.root / here / first).is_dir()
    ):
        return None  # names a path of the repo the plugin runs in
    return [(plugin / token).as_posix(), (here / token).as_posix()]


def _missing_ref(
    repo: Repo, rel: str, token: str, plugins: dict[str, Path], known: set[str]
) -> bool:
    command = COMMAND_RE.match(token)
    if command:
        root = plugins.get(command.group(1))
        return root is not None and not (repo.root / root / "skills" / command.group(2)).is_dir()
    candidates = _ref_candidates(repo, rel, token)
    return candidates is not None and not any(_exists(repo, c, known) for c in candidates)


def check_ref_paths(repo: Repo) -> None:
    plugins = _plugin_names(repo)
    # Every directory and file, and every tail of their paths: rules abbreviate a path from inside
    # its subtree (`app/crud/` for `apps/backend/app/crud/`), which a reader resolves the same way.
    known: set[str] = set()
    for f in repo.files:
        parts = f.split("/")
        for end in range(1, len(parts) + 1):
            for start in range(end):
                known.add("/".join(parts[start:end]))
    sources = set(instruction_texts(repo)) | set(repo.instruction_paths(is_agent_definition(repo)))
    for rel in sorted(sources):
        fenced = False
        for number, line in enumerate(repo.text(rel).splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            if fenced or "<!-- ref-ok -->" in line:
                continue
            for match in CODE_SPAN_RE.finditer(line):
                token = match.group(1).strip()
                if _missing_ref(repo, rel, token, plugins, known):
                    repo.warn("ref-path-missing", f"{rel}:{number}", f"`{token}` does not exist")


def run(root: Path) -> Repo:
    budget, exclude = load_config(root)
    repo = Repo(root=root, budget=budget, exclude=exclude, files=rule_loading.list_files(root))
    check_rules(repo)
    check_instruction_files(repo)
    check_skills(repo)
    check_agents(repo)
    check_ref_paths(repo)
    return repo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", help="repo root (default: the git toplevel, else cwd)")
    parser.add_argument("--json", action="store_true", help="one JSON list of findings")
    args = parser.parse_args()
    repo = run(rule_loading.repo_root(args.root))
    errors = [f for f in repo.findings if f.severity == "error"]
    if args.json:
        print(json.dumps([asdict(f) for f in repo.findings], indent=2))
        return 1 if errors else 0
    for finding in repo.findings:
        mark = "✗" if finding.severity == "error" else "!"
        print(f"{mark} {finding.path}: {finding.message} [{finding.check}]")
    if yaml is None:
        print("! PyYAML not installed: strict-YAML checks skipped (pip install pyyaml)")
    print(f"{len(errors)} error(s), {len(repo.findings) - len(errors)} warning(s)")
    if errors and not repo.exclude:
        print(
            "Trees of product content or archives (their own SKILL.md or AGENTS.md, not Claude "
            'Code instructions)? Exclude them: .weside/config.json → {"optimization": '
            '{"exclude": ["<dir>"]}}'
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
