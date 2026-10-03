"""Claude Code's rule-loading semantics, once: which `.claude/rules/**/*.md` apply to which file.

Every tool that asks "does this rule load for that file" imports this module instead of
re-implementing it: `load-rules.py` (the bridge for agents other than Claude Code), the budget
gate `check-instruction-budget.py`, and any repo script outside the plugin. The behaviour is
pinned by golden fixtures recorded from real `claude -p` runs (`fixtures/rule-loading.json`,
recorded by `probe-rule-loading.py`, replayed by `test_rule_loading.py`).

Semantics, as measured:

- Frontmatter is YAML. When it fails to parse, Claude Code quotes the problematic `key: value`
  values and parses again; only frontmatter that still fails is dropped, and the rule then loads
  unconditionally. An unterminated `---` block is no frontmatter at all.
- `paths:` is a list or a comma-separated string. Absent or empty → the rule always loads.
  `globs:` is not read.
- Brace groups expand first (`*.{ts,tsx}`), with a budget of 1,000 expanded patterns per rule;
  a pattern over the remaining budget stays whole and its literal braces match nothing.
- Each expanded pattern matches with gitignore semantics: without a `/` (other than a trailing
  one) it matches a name at any depth (`*.md` matches `docs/a.md`); with one it is anchored at
  the repo root (`src/*.py` does not match `src/deep/mod.py`). `*` and `?` stay inside one
  segment, `**/` also matches zero directories, a pattern that matches a directory matches
  everything below it, and a trailing `/` matches directories only.
- A `!` pattern excludes nothing, and an invalid pattern (`[z-a]`, an unclosed `[`) matches
  nothing.

API: `load_rules(root)`, `load_rule(path)`, `parse_rule(text)`, `Rule.applies_to(path)`,
`Rule.match_reason(path)`, `applicable(rules, files)`, `pattern_matches(pattern, path)`,
`expand_paths(patterns)`, `list_files(root)`, `repo_root()`, `normalize_path(path, root)`.
Import it by path — `sys.path.insert(0, <plugin>/scripts)` then `import rule_loading`.
Stdlib only; PyYAML, when installed, makes the YAML step exact (`Rule.yaml_checked`).
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only where PyYAML is absent
    yaml = None

BRACE_BUDGET = 1000  # memory.md: a rule's `paths` list shares 1,000 expanded patterns
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__"}


@dataclass(frozen=True)
class Rule:
    path: Path | None
    description: str | None
    patterns: tuple[str, ...]
    defect: str | None = None  # why the frontmatter is not what it looks like
    unconditional: bool = False  # frontmatter dropped: loads for every file
    yaml_checked: bool = True  # False: PyYAML absent, YAML failures not detected

    @property
    def is_always_on(self) -> bool:
        return self.unconditional or not self.patterns

    def match_reason(self, path: str) -> str | None:
        """The pattern (and its brace expansion) that loads this rule for `path`, else None."""
        if self.is_always_on:
            return "always-on"
        for pattern in self.patterns:
            reason = _pattern_reason(pattern, path, self.patterns)
            if reason is not None:
                return reason
        return None

    def applies_to(self, path: str) -> bool:
        return self.match_reason(path) is not None


# --- frontmatter -------------------------------------------------------------------------------


def frontmatter_block(text: str) -> str | None:
    """The text between the opening and closing `---`; None when absent or unterminated."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            return "\n".join(lines[1:index])
    return None


_PROBLEM_CHARS = set("{}[]*&!|>%@`#")
_KEY_VALUE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s+(.+?)\s*$")


def _quote_problematic(block: str) -> str:
    """Claude Code's retry: top-level `key: value` lines whose value YAML would misread get quoted."""
    out = []
    for line in block.splitlines():
        match = _KEY_VALUE.match(line)
        value = match.group(2) if match else ""
        if (
            match
            and value[0] not in "\"'"
            and (value[0] in _PROBLEM_CHARS or ": " in value or " #" in value)
        ):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            out.append(f'{match.group(1)}: "{escaped}"')
            continue
        out.append(line)
    return "\n".join(out)


def _yaml_mapping(block: str) -> dict | None:
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else {}


def _lenient_mapping(block: str) -> dict[str, object]:
    """Top-level keys, inline lists and `- item` lists; used only where PyYAML is absent."""
    data: dict[str, object] = {}
    current: str | None = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")) and ":" in line:
            key, value = (part.strip() for part in line.split(":", 1))
            current = key
            if not value:
                data[key] = []
            elif value.startswith("[") and value.endswith("]"):
                data[key] = [item.strip().strip("\"'") for item in _split_commas(value[1:-1])]
            else:
                data[key] = value.strip("\"'")
            continue
        stripped = line.strip()
        if current and isinstance(data.get(current), list) and stripped.startswith("- "):
            item = stripped[2:].strip()
            if item and item[0] in "*&!|>%@`":
                raise ValueError(item)  # YAML rejects it, and quoting repairs only `key: value`
            data[current].append(item.strip("\"'"))
    return data


def split_paths(value: object) -> tuple[str, ...]:
    """`paths:` as Claude Code reads it: a list, or one comma-separated string."""
    if isinstance(value, str):
        items = _split_commas(value)
    elif isinstance(value, list):
        items = [str(item) for item in value if item is not None]
    else:
        return ()
    return tuple(item.strip() for item in items if item.strip())


def parse_rule(text: str, path: Path | None = None) -> Rule:
    lines = text.splitlines()
    block = frontmatter_block(text)
    if block is None:
        defect = None
        if lines and lines[0].rstrip() == "---":
            defect = "unterminated frontmatter — no frontmatter at all, the rule always loads"
        return Rule(path=path, description=None, patterns=(), defect=defect)

    defect = None
    unconditional = False
    yaml_checked = yaml is not None
    if yaml is None:
        try:
            data: dict = _lenient_mapping(block)
        except ValueError:
            data = {}
            unconditional = True
            defect = "an unquoted list item YAML cannot read — the rule always loads"
    else:
        data = _yaml_mapping(block)
        if data is None:
            data = _yaml_mapping(_quote_problematic(block))
            if data is None:
                data = {}
                unconditional = True
                defect = "frontmatter is not valid YAML even with its values quoted — the rule always loads"
            else:
                defect = (
                    "frontmatter is not valid YAML; Claude Code reads it with the values quoted"
                )

    patterns = split_paths(data.get("paths"))
    if "globs" in data and "paths" not in data and not unconditional:
        defect = defect or "`globs:` is not `paths:` — the rule always loads"
    description = data.get("description")
    return Rule(
        path=path,
        description=str(description) if description else None,
        patterns=patterns,
        defect=defect,
        unconditional=unconditional,
        yaml_checked=yaml_checked,
    )


def load_rule(path: Path) -> Rule:
    return parse_rule(path.read_text(encoding="utf-8"), path)


def load_rules(root: Path) -> list[Rule]:
    """Every `.claude/rules/**/*.md` under `root`, sorted by path."""
    rules_dir = root / ".claude" / "rules"
    if not rules_dir.is_dir():
        return []
    return [load_rule(path) for path in sorted(rules_dir.rglob("*.md"))]


# --- brace expansion ---------------------------------------------------------------------------


def _split_commas(text: str) -> list[str]:
    """Split on commas outside braces: `a/*.{ts,tsx}, b/**` is two patterns."""
    parts, depth, current = [], 0, ""
    for char in text:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)  # a stray `}` must not swallow later commas
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def _parse_braces(text: str) -> list:
    """Literal strings and brace groups; a group is a list of option sequences.

    `{a}` (one option) and an unmatched `{` stay literal, as in bash.
    """
    sequence: list = []
    literal, index = "", 0
    while index < len(text):
        if text[index] == "{":
            depth, close = 0, -1
            for probe in range(index, len(text)):
                if text[probe] == "{":
                    depth += 1
                elif text[probe] == "}":
                    depth -= 1
                    if depth == 0:
                        close = probe
                        break
            options = _split_commas(text[index + 1 : close]) if close != -1 else []
            if len(options) >= 2:
                if literal:
                    sequence.append(literal)
                    literal = ""
                sequence.append([_parse_braces(option) for option in options])
                index = close + 1
                continue
        literal += text[index]
        index += 1
    if literal:
        sequence.append(literal)
    return sequence


def _count(sequence: list) -> int:
    total = 1
    for part in sequence:
        if isinstance(part, list):
            total *= sum(_count(option) for option in part)
    return total


def _expand(sequence: list) -> list[str]:
    results = [""]
    for part in sequence:
        if isinstance(part, str):
            results = [prefix + part for prefix in results]
        else:
            options = [text for option in part for text in _expand(option)]
            results = [prefix + option for prefix in results for option in options]
    return results


@functools.lru_cache(maxsize=1024)
def expand_paths(
    patterns: tuple[str, ...], budget: int = BRACE_BUDGET
) -> dict[str, tuple[str, ...]]:
    """Every pattern of one rule's `paths:` with its brace expansion.

    The list shares one budget; patterns without braces cost nothing. A pattern whose expansion
    would exceed what is left stays whole. Counting happens before expanding.
    """
    result: dict[str, tuple[str, ...]] = {}
    used = 0
    for pattern in patterns:
        sequence = _parse_braces(pattern)
        if all(isinstance(part, str) for part in sequence):
            result[pattern] = (pattern,)
            continue
        count = _count(sequence)
        if used + count > budget:
            result[pattern] = (pattern,)
            continue
        used += count
        result[pattern] = tuple(_expand(sequence))
    return result


def expand_braces(pattern: str, budget: int = BRACE_BUDGET) -> list[str]:
    return list(expand_paths((pattern,), budget)[pattern])


# --- matching ----------------------------------------------------------------------------------


def _segment_regex(pattern: str) -> str | None:
    """`*`/`?`/`[...]`/`\\x` inside segments; `**` only as a whole segment. None = invalid."""
    out, index = "", 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index) and (index == 0 or pattern[index - 1] == "/"):
            out += "(?:[^/]+/)*"
            index += 3
            continue
        if (
            pattern.startswith("**", index)
            and index + 2 == len(pattern)
            and pattern[index - 1 : index] in ("/", "")
        ):
            out += ".*"
            index += 2
            continue
        if char == "*":
            out += "[^/]*"
        elif char == "?":
            out += "[^/]"
        elif char == "\\" and index + 1 < len(pattern):
            index += 1
            out += re.escape(pattern[index])
        elif char == "[":
            close = pattern.find("]", index + 2)
            if close == -1:
                return None
            body = pattern[index + 1 : close]
            if body.startswith("!"):
                body = "^" + body[1:]
            out += f"[{body}]"
            index = close
        else:
            out += re.escape(char)
        index += 1
    return out


@functools.lru_cache(maxsize=4096)
def _compile(pattern: str) -> tuple[re.Pattern[str], bool] | None:
    """(regex, directory-only) for one expanded pattern, gitignore-style; None matches nothing."""
    if not pattern or pattern.startswith("!"):
        return None
    dir_only = pattern.endswith("/")
    body = pattern.rstrip("/")
    anchored = "/" in body
    body = body.lstrip("/")
    if not body:
        return None
    regex = _segment_regex(body)
    if regex is None:
        return None
    try:
        compiled = re.compile(("" if anchored else "(?:[^/]+/)*") + regex + r"\Z")
    except re.error:  # `[z-a]`: an invalid bracket expression matches nothing
        return None
    return compiled, dir_only


def _expanded_matches(expanded: str, path: str) -> bool:
    compiled = _compile(expanded)
    if compiled is None:
        return False
    regex, dir_only = compiled
    parts = path.split("/")
    candidates = ["/".join(parts[:end]) for end in range(1, len(parts))]  # ancestor dirs
    if not dir_only:
        candidates.append(path)
    return any(regex.match(candidate) for candidate in candidates)


def _pattern_reason(pattern: str, path: str, rule_patterns: tuple[str, ...]) -> str | None:
    path = path.removeprefix("./")
    patterns = rule_patterns or (pattern,)
    for expanded in expand_paths(patterns).get(pattern, (pattern,)):
        if _expanded_matches(expanded, path):
            return f"`{pattern}`" if expanded == pattern else f"`{pattern}` via `{expanded}`"
    return None


def pattern_matches(pattern: str, path: str, rule_patterns: tuple[str, ...] = ()) -> bool:
    """`rule_patterns` is the whole `paths:` list the pattern belongs to (shared brace budget)."""
    return _pattern_reason(pattern, path, rule_patterns) is not None


def applicable(rules: list[Rule], files: list[str]) -> tuple[list[Rule], list[Rule]]:
    """(always-on rules, rules a path-match loads for at least one of `files`)."""
    always_on = [rule for rule in rules if rule.is_always_on]
    matched = [
        rule
        for rule in rules
        if not rule.is_always_on and any(rule.applies_to(file) for file in files)
    ]
    return always_on, matched


# --- repo --------------------------------------------------------------------------------------


def repo_root(explicit: str | None = None) -> Path:
    """`explicit`, else the git toplevel of the cwd (a worktree answers with its own), else cwd."""
    if explicit:
        return Path(explicit).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return Path.cwd().resolve()


def list_files(root: Path) -> list[str]:
    """Tracked plus untracked-not-ignored files (`git ls-files -co`); a plain walk outside git."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "-co", "--exclude-standard"],  # -z: no C-quoted paths
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        listed = {name for name in result.stdout.split("\0") if name}
        return sorted(rel for rel in listed if (root / rel).is_file())
    found = []
    for directory, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_dir = Path(directory).relative_to(root).as_posix()
        found.extend(name if rel_dir == "." else f"{rel_dir}/{name}" for name in names)
    return sorted(found)


def normalize_path(path: str, root: Path) -> str:
    """Repo-relative. A relative argument resolves against the CURRENT directory, not the root:
    standing in `apps/backend`, `app/main.py` means that file."""
    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else (Path.cwd() / candidate)
    try:
        return absolute.resolve().relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix().removeprefix("./")
