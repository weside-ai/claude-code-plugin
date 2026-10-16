"""test-delta.py: the PR body's test line counts definitions from the merge base, moves cancel.

Run: `python3 -m pytest -q we/scripts/test_test_delta.py`
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("test-delta.py")
_spec = importlib.util.spec_from_file_location("test_delta", SCRIPT)
delta = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(delta)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def _commit(repo: Path, files: dict[str, str | None], msg: str) -> None:
    for name, text in files.items():
        path = repo / name
        if text is None:
            _git(repo, "rm", "-q", name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        _git(repo, "add", name)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg)


def _run(repo: Path, base: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), base], cwd=repo, capture_output=True, text=True, check=False
    )


OLD_PY = "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n\n\ndef helper():\n    pass\n"
MOVED = "".join(f"def test_moved_{i}():\n    assert {i}\n\n\n" for i in range(5))


def test_counts_added_and_removed_and_cancels_moves(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, {"tests/test_old.py": OLD_PY, "tests/test_moved.py": MOVED}, "base")
    _git(repo, "checkout", "-qb", "feat")
    new_py = (
        OLD_PY.replace("def test_a():", "def test_a(  ):").replace(  # reformatted: cancels
            "def test_b():\n    pass\n", ""
        )  # removed
        + "\n\nasync def test_c():\n    pass\n\n\nclass T:\n    def test_d(self):\n        pass\n"
    )
    js = "describe('x', () => {\n  it('works', () => {});\n  test.each([1])('n %i', () => {});\n});\n"
    _commit(
        repo,
        {
            "tests/test_old.py": new_py,
            "tests/test_moved.py": None,
            "tests/sub/test_moved.py": MOVED,  # moved file: cancels
            "web/a.test.ts": js,
            "README.md": "def test_not_counted():\n  it('nor this', x)\n",
        },
        "feat",
    )
    out = _run(repo, "main")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "Tests: +4 / -1 (net +3)"


def test_render_signs() -> None:
    assert delta.render(0, 0) == "Tests: +0 / -0 (net ±0)"
    assert delta.render(1, 4) == "Tests: +1 / -4 (net -3)"


def test_bad_base_fails_with_message(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, {"a.py": "x = 1\n"}, "base")
    out = _run(repo, "no-such-ref")
    assert out.returncode == 1
    assert "test-delta: git diff failed" in out.stderr
