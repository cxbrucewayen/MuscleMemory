import shutil
from pathlib import Path

import pytest

from musclememory.cards import KB, load_yaml
from musclememory.drivers.sim import SimDriver

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "demo"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """A private copy of the demo library, with secrets kept in a temp home."""
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("runs"))
    monkeypatch.setenv("CUA_EXPERIENCE_HOME", str(tmp_path / "home"))
    return root


@pytest.fixture
def kb(demo):
    return KB.load(demo)


def sim(root, name="windows-4.1", mutate=None):
    spec = load_yaml((root / "sim" / f"{name}.yaml").read_text(encoding="utf-8"))
    if mutate:
        mutate(spec)
    return SimDriver(spec)


def write_lib(root: Path, files: dict[str, str]) -> KB:
    """Create a tiny library from {relative path: yaml text}."""
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return KB.load(root)


def rules(issues) -> set[str]:
    return {i.rule for i in issues}
