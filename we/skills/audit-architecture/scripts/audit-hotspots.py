#!/usr/bin/env python3
"""Architecture Hotspot Heatmap — Phase 1 of /we:audit-architecture v3.

Idea:
  Architectural problem zones emerge where many Platform Primitives compose
  in a single module. Pure LOC / churn metrics miss the architectural
  signal; primitive density catches it.

Method:
  For each backend Python file:
    - count Primitives composed (via YAML-driven regex catalog)
    - count *-BYPASS-OK annotations
    - LOC
    - 6-month git churn (commit count)
    - vendor-import leaks outside configured encapsulation homes
    - private-module reach-ins (imports of `_*` symbols outside the private root)

  score = primitives*5 + LOC/50 + churn + bypasses*3 + reach-ins*3 + leaks*4

  Top-N by score is the candidate list of architectural hotspots.
  Expected-vs-unexpected classification: a file path matching `expected_hubs`
  in the project config is a documented density-hub (no surprise);
  everything else is a candidate for Phase-3 architectural-significance review.

Configuration:
  Project config (`docs/.audit-architecture.yml`) drives:
    - backend_root         (path to scan; default `apps/backend/app`)
    - hotspots.top_n       (default 15)
    - hotspots.since       (default "6 months ago")
    - hotspots.expected_hubs (list of paths)
    - primitive_detectors  (project-specific override of the catalog)
    - hotspots.encapsulation_homes (override default vendor home-paths)
    - hotspots.private_module_root (override default _-prefix root)

  Plugin default catalog at `<plugin>/scripts/primitives.default.yml`.

Usage:
  python3 audit-hotspots.py                                # full scan, top-15 to stdout
  python3 audit-hotspots.py --top 30                       # show top-30
  python3 audit-hotspots.py --file <path>                  # detailed breakdown for ONE file
  python3 audit-hotspots.py --write                        # write MD to <findings_dir>
  python3 audit-hotspots.py --project-config <path>        # explicit project YAML
  python3 audit-hotspots.py --primitives-catalog <path>    # explicit primitives YAML
  python3 audit-hotspots.py --backend-root <path>          # override scan root
  python3 audit-hotspots.py --since "1 year ago"           # custom churn window
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML not installed. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)


# ---------------------------------------------------------------------- defaults

DEFAULT_BACKEND_ROOT = Path("apps/backend/app")
DEFAULT_PROJECT_CONFIG = Path("docs/.audit-architecture.yml")
DEFAULT_TOP_N = 15
DEFAULT_SINCE = "6 months ago"

BYPASS_RE = re.compile(r"#\s*(PRIMITIVE|CRUD|SESSION|METERING|COMPACTION)-BYPASS-OK")


# ---------------------------------------------------------------------- config


@dataclass
class HotspotConfig:
    backend_root: Path
    primitive_detectors: list[tuple[str, list[re.Pattern[str]]]]
    expected_hubs: set[str]
    encapsulation_homes: dict[str, list[str]]
    private_module_root: str
    top_n: int
    since: str
    findings_dir: Path
    diagrams_dir: Path

    @property
    def private_module_root_python(self) -> str:
        """Convert path-form to Python-import-form for reach-in regex."""
        return self.private_module_root.replace("/", ".").rstrip(".")

    def is_in_encapsulation_home(self, file_path: Path, vendor: str) -> bool:
        """True iff file_path is inside any home configured for this vendor."""
        s = str(file_path).replace("\\", "/")
        homes = self.encapsulation_homes.get(vendor, [])
        return any(s.startswith(h) or s == h.rstrip("/") for h in homes)

    def is_inside_private_root(self, file_path: Path) -> bool:
        s = str(file_path).replace("\\", "/")
        root = self.private_module_root.rstrip("/")
        return s.startswith(root + "/") or s == root


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"ERROR parsing {path}: {e}", file=sys.stderr)
        sys.exit(2)


def _compile_detectors(
    detector_list: list[dict[str, Any]],
) -> list[tuple[str, list[re.Pattern[str]]]]:
    """Compile YAML detector entries into (name, [patterns]) tuples."""
    compiled: list[tuple[str, list[re.Pattern[str]]]] = []
    for entry in detector_list:
        name = entry.get("name")
        patterns = entry.get("patterns", [])
        if not name or not patterns:
            continue
        compiled_patterns = [re.compile(p) for p in patterns]
        compiled.append((name, compiled_patterns))
    return compiled


def load_config(
    project_config_path: Path,
    primitives_catalog_path: Path,
    backend_root_override: Path | None,
    top_n_override: int | None,
    since_override: str | None,
) -> HotspotConfig:
    """Load + merge plugin default catalog and project config."""
    catalog = _load_yaml(primitives_catalog_path)
    project = _load_yaml(project_config_path)

    catalog_detectors = catalog.get("primitives", []) or []
    project_detectors = project.get("primitive_detectors", []) or []

    # Merge: project entries override catalog entries with the same name
    detector_map: dict[str, dict[str, Any]] = {}
    for entry in catalog_detectors:
        if name := entry.get("name"):
            detector_map[name] = entry
    for entry in project_detectors:
        if name := entry.get("name"):
            detector_map[name] = entry

    detectors = _compile_detectors(list(detector_map.values()))

    hotspots_block = project.get("hotspots", {}) or {}
    expected_hubs = set(hotspots_block.get("expected_hubs", []) or [])

    encapsulation_homes = (
        hotspots_block.get("encapsulation_homes") or catalog.get("encapsulation_homes", {}) or {}
    )
    private_module_root = (
        hotspots_block.get("private_module_root") or catalog.get("private_module_root", "") or ""
    )

    backend_root = backend_root_override or Path(
        project.get("backend_root", str(DEFAULT_BACKEND_ROOT))
    )
    top_n = top_n_override or hotspots_block.get("top_n", DEFAULT_TOP_N)
    since = since_override or hotspots_block.get("since", DEFAULT_SINCE)
    findings_dir = Path(project.get("findings_dir", "docs/audits/"))
    diagrams_dir = Path(project.get("diagrams_dir", "docs/architecture/diagrams/"))

    return HotspotConfig(
        backend_root=backend_root,
        primitive_detectors=detectors,
        expected_hubs=expected_hubs,
        encapsulation_homes=encapsulation_homes,
        private_module_root=private_module_root,
        top_n=top_n,
        since=since,
        findings_dir=findings_dir,
        diagrams_dir=diagrams_dir,
    )


# ---------------------------------------------------------------------- scan


@dataclass
class FileScan:
    path: Path
    loc: int = 0
    primitives: list[str] = field(default_factory=list)
    bypass_count: int = 0
    vendor_leaks: dict[str, int] = field(default_factory=dict)  # vendor -> count
    private_reach_ins: int = 0
    churn: int = 0
    score: float = 0.0
    expected: bool = False

    @property
    def total_leaks(self) -> int:
        return sum(self.vendor_leaks.values())

    def compute_score(self) -> None:
        self.score = (
            len(self.primitives) * 5
            + self.loc / 50
            + self.churn
            + self.bypass_count * 3
            + self.private_reach_ins * 3
            + self.total_leaks * 4
        )


def scan_file(path: Path, cfg: HotspotConfig) -> FileScan:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fs = FileScan(path=path)
    fs.loc = len(text.splitlines())

    # Primitive detection (catalog-driven)
    for name, compiled_patterns in cfg.primitive_detectors:
        for cp in compiled_patterns:
            if cp.search(text):
                fs.primitives.append(name)
                break

    # Bypass annotations
    fs.bypass_count = len(BYPASS_RE.findall(text))

    # Vendor leaks: for each configured vendor, count `from <vendor>` imports
    # IF the file is NOT inside a home configured for that vendor.
    for vendor in cfg.encapsulation_homes:
        if cfg.is_in_encapsulation_home(path, vendor):
            continue
        leak_re = re.compile(rf"^\s*from {re.escape(vendor)}", re.MULTILINE)
        leaks = len(leak_re.findall(text))
        if leaks > 0:
            fs.vendor_leaks[vendor] = leaks

    # Private reach-ins: only count if the file is NOT inside the private root
    if cfg.private_module_root and not cfg.is_inside_private_root(path):
        py_root = cfg.private_module_root_python
        reach_re = re.compile(rf"from {re.escape(py_root)}\._\w+ import")
        fs.private_reach_ins = len(reach_re.findall(text))

    # Expected-hub classification
    fs.expected = str(path).replace("\\", "/") in cfg.expected_hubs

    return fs


def get_all_churn(since: str) -> dict[str, int]:
    """Return {relative_path_str: commit_count} via single git log call."""
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={since}",
                "--name-only",
                "--pretty=format:__COMMIT__",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"WARNING: git log returned {result.returncode}; churn will be 0.",
                file=sys.stderr,
            )
            return {}
    except (OSError, subprocess.SubprocessError) as e:
        print(f"WARNING: git log failed: {e}; churn will be 0.", file=sys.stderr)
        return {}

    counts: dict[str, int] = {}
    seen_in_commit: set[str] = set()
    for line in result.stdout.splitlines():
        if line.startswith("__COMMIT__"):
            seen_in_commit = set()
            continue
        if not line.strip():
            continue
        if line in seen_in_commit:
            continue
        seen_in_commit.add(line)
        counts[line] = counts.get(line, 0) + 1
    return counts


# ---------------------------------------------------------------------- output


def _frontmatter(today: str) -> list[str]:
    return [
        "---",
        "type: audit",
        "domain: [platform]",
        "status: current",
        "scope: hotspots",
        f"date: {today}",
        "---",
        "",
    ]


def _score_formula_block() -> list[str]:
    return [
        "## Score formula",
        "",
        "```",
        "score = primitives * 5     # Platform Primitives composed",
        "      + LOC / 50           # file size as complexity proxy",
        "      + churn              # git commits in window",
        "      + bypasses * 3       # # *-BYPASS-OK: knowing-divergence count",
        "      + reach-ins * 3      # `from <core>._*` outside core",
        "      + leaks * 4          # `from <vendor>` outside configured homes",
        "```",
        "",
        "Score ≠ finding. High score = candidate for deep-read. The audit move",
        "is **expected-vs-unexpected**: which top-scored files are documented",
        "hubs (✓ = `expected_hubs` in config), which are surprises?",
        "",
    ]


def _rel_path(path: Path) -> Path:
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def _table_row(idx: int, fs: FileScan) -> str:
    rel = _rel_path(fs.path)
    hub = "✓" if fs.expected else " "
    return (
        f"| {idx} | `{rel}` | {hub} | {fs.score:.0f} | "
        f"{len(fs.primitives)} | {fs.loc} | "
        f"{fs.churn} | {fs.bypass_count} | {fs.total_leaks} | "
        f"{fs.private_reach_ins} |"
    )


def _table_block(top: list[FileScan]) -> list[str]:
    lines = [
        f"## Top {len(top)} by composite score",
        "",
        "| # | File | Hub? | Score | Prim | LOC | Churn | Byp | Leak | Reach |",
        "|---|---|:---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(_table_row(i, fs) for i, fs in enumerate(top, 1))
    lines.append("")
    return lines


def _surprise_block(top: list[FileScan], cfg: HotspotConfig) -> list[str]:
    surprises = [fs for fs in top if not fs.expected]
    if not surprises:
        return []
    lines = [
        f"## Surprise hotspots ({len(surprises)} of top {len(top)})",
        "",
        "Files in the top-N **NOT** marked as documented hubs — candidates for "
        "Phase-3 architectural-significance deep-read.",
        "",
    ]
    for fs in surprises[:5]:
        lines.extend(_surprise_entry(fs, cfg))
    return lines


def _surprise_entry(fs: FileScan, cfg: HotspotConfig) -> list[str]:
    rel = _rel_path(fs.path)
    block = [
        f"### `{rel}` (score {fs.score:.0f})",
        "",
        f"- **Primitives ({len(fs.primitives)}):** " + ", ".join(f"`{p}`" for p in fs.primitives),
        f"- **LOC:** {fs.loc}",
        f"- **Churn ({cfg.since}):** {fs.churn} commits",
        f"- **`*-BYPASS-OK` annotations:** {fs.bypass_count}",
    ]
    if fs.vendor_leaks:
        leak_str = ", ".join(f"`{v}`={c}" for v, c in fs.vendor_leaks.items())
        block.append(f"- **Vendor leaks:** {leak_str}")
    if fs.private_reach_ins:
        block.append(f"- **`{cfg.private_module_root}/_*` reach-ins:** {fs.private_reach_ins}")
    block.append("")
    return block


def render_table(top: list[FileScan], total: int, cfg: HotspotConfig) -> str:
    today = datetime.now(UTC).date().isoformat()
    lines: list[str] = []
    lines.extend(_frontmatter(today))
    lines.append(f"# Architecture Hotspot Heatmap — {today}")
    lines.append("")
    lines.append(
        f"Scanned **{total}** Python files under `{cfg.backend_root}` "
        f"(excluding tests, migrations, `__init__.py`). "
        f"Churn window: **{cfg.since}**."
    )
    lines.append("")
    lines.extend(_score_formula_block())
    lines.extend(_table_block(top))
    lines.extend(_surprise_block(top, cfg))
    lines.append("## Per-file deep-dive")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 audit-hotspots.py --file <path>")
    lines.append("```")
    return "\n".join(lines)


def print_detailed(fs: FileScan, cfg: HotspotConfig) -> None:
    print(f"# {fs.path}")
    print()
    print(f"Score: {fs.score:.1f}")
    print(f"Expected hub: {fs.expected}")
    print(f"LOC: {fs.loc}")
    print(f"Churn ({cfg.since}): {fs.churn} commits")
    print()
    print(f"Primitives composed ({len(fs.primitives)}):")
    for p in fs.primitives:
        print(f"  - {p}")
    print()
    print(f"`*-BYPASS-OK` annotations: {fs.bypass_count}")
    if fs.vendor_leaks:
        print("Vendor-leaks (outside configured homes):")
        for vendor, count in fs.vendor_leaks.items():
            print(f"  - {vendor}: {count}")
    else:
        print("Vendor-leaks: none")
    print(f"`{cfg.private_module_root}/_*` private reach-ins: {fs.private_reach_ins}")


# ---------------------------------------------------------------------- main


def _resolve_primitives_catalog(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    # Default: sibling file of this script
    return Path(__file__).parent / "primitives.default.yml"


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write findings MD to <findings_dir>/<date>-hotspots.md",
    )
    parser.add_argument(
        "--top", type=int, default=None, help="Show top-N (default from config or 15)"
    )
    parser.add_argument("--file", type=str, help="Detailed breakdown for ONE file (no full scan)")
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Churn window (default from config or '6 months ago')",
    )
    parser.add_argument(
        "--project-config",
        type=str,
        default=str(DEFAULT_PROJECT_CONFIG),
        help=f"Project YAML (default: {DEFAULT_PROJECT_CONFIG})",
    )
    parser.add_argument(
        "--primitives-catalog",
        type=str,
        default=None,
        help="Primitive-detector catalog YAML (default: plugin's primitives.default.yml)",
    )
    parser.add_argument(
        "--backend-root",
        type=str,
        default=None,
        help="Override backend root path (default from config or apps/backend/app)",
    )
    return parser


def _file_mode(args: argparse.Namespace, cfg: HotspotConfig) -> None:
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    fs = scan_file(path, cfg)
    churn = get_all_churn(cfg.since)
    fs.churn = churn.get(str(path).replace("\\", "/"), 0)
    fs.compute_score()
    print_detailed(fs, cfg)


def _is_skip_path(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return True
    s = str(path).replace("\\", "/")
    if "/tests/" in s:
        return True
    if "/migrations/" in s or "/alembic/" in s:
        return True
    return path.name == "__init__.py"


def _scan_all(cfg: HotspotConfig) -> list[FileScan]:
    scans: list[FileScan] = []
    for path in sorted(cfg.backend_root.rglob("*.py")):
        if _is_skip_path(path):
            continue
        scans.append(scan_file(path, cfg))
    print(f"# Computing churn ({cfg.since}) for {len(scans)} files...", file=sys.stderr)
    churn = get_all_churn(cfg.since)
    for fs in scans:
        fs.churn = churn.get(str(fs.path).replace("\\", "/"), 0)
        fs.compute_score()
    scans.sort(key=lambda f: f.score, reverse=True)
    return scans


def main() -> None:
    args = _build_argparser().parse_args()

    cfg = load_config(
        project_config_path=Path(args.project_config),
        primitives_catalog_path=_resolve_primitives_catalog(args.primitives_catalog),
        backend_root_override=Path(args.backend_root) if args.backend_root else None,
        top_n_override=args.top,
        since_override=args.since,
    )

    if args.file:
        _file_mode(args, cfg)
        return

    if not cfg.backend_root.exists():
        print(f"Backend root not found: {cfg.backend_root.resolve()}", file=sys.stderr)
        print("Run from repo root, or pass --backend-root <path>.", file=sys.stderr)
        sys.exit(1)

    if not cfg.primitive_detectors:
        print(
            "WARNING: no primitive detectors loaded. Score will be density-only.",
            file=sys.stderr,
        )

    scans = _scan_all(cfg)
    top = scans[: cfg.top_n]
    out = render_table(top, len(scans), cfg)

    if args.write:
        today = datetime.now(UTC).date().isoformat()
        out_path = cfg.findings_dir / f"{today}-hotspots.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
        print(f"Wrote: {out_path}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
