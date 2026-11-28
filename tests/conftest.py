"""
Global pytest configuration and hermeticity guards (`tests/conftest.py`).
Ensures running `uv run pytest` NEVER modifies `data/nba_intelligence.sqlite3`,
`docs/index.html`, `SEGUIMIENTO_APUESTAS.md`, `reports/`, or `NBA/` in the working tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

from src.storage.db import DatabaseManager
from tests.helpers import PROJECT_ROOT, copy_prod_db

_PROTECTED_FILES = {
    (PROJECT_ROOT / "docs" / "index.html").resolve(),
    (PROJECT_ROOT / "SEGUIMIENTO_APUESTAS.md").resolve(),
    (PROJECT_ROOT / "data" / "apuestas_historial.csv").resolve(),
    (PROJECT_ROOT / "data" / "alert_state.json").resolve(),
    (PROJECT_ROOT / "data" / "telegram_offset.txt").resolve(),
    (PROJECT_ROOT / "config" / "calibrated_weights.json").resolve(),
}

_PROTECTED_DIRS = (
    (PROJECT_ROOT / "docs").resolve(),
    (PROJECT_ROOT / "reports").resolve(),
    (PROJECT_ROOT / "NBA").resolve(),
    (PROJECT_ROOT / "data" / "evaluation").resolve(),
    (PROJECT_ROOT / "data" / "visual_rag").resolve(),
)

_PROD_DB_RESOLVED = (PROJECT_ROOT / "data" / "nba_intelligence.sqlite3").resolve()


def _should_redirect_repo_write(resolved_path: Path) -> bool:
    if resolved_path in _PROTECTED_FILES:
        return True
    for pdir in _PROTECTED_DIRS:
        if resolved_path == pdir or pdir in resolved_path.parents:
            return True
    return False


@pytest.fixture(autouse=True)
def _hermetic_worktree_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Guarantees 100% test suite hermeticity:
    1. Redirects any accidental `DatabaseManager` pointing at `data/nba_intelligence.sqlite3`
       to an isolated temporary copy in `tmp_path`.
    2. Redirects any `Path.write_text` / `Path.write_bytes` targeting tracked repository outputs
       (`docs/index.html`, `reports/`, `NBA/`, `SEGUIMIENTO_APUESTAS.md`, etc.) into `tmp_path`.
    """
    orig_db_init = DatabaseManager.__init__

    def _safe_db_init(self: DatabaseManager, db_path: str | Path = "data/nba_intelligence.sqlite3") -> None:
        resolved = Path(db_path).resolve()
        if resolved == _PROD_DB_RESOLVED:
            db_path = copy_prod_db(tmp_path, "hermetic_db_copy.sqlite3")
        orig_db_init(self, db_path)

    monkeypatch.setattr(DatabaseManager, "__init__", _safe_db_init)

    orig_write_text = Path.write_text
    orig_write_bytes = Path.write_bytes

    def _redirect_target(target: Path) -> Path:
        try:
            resolved = target.resolve()
        except OSError:
            return target
        if _should_redirect_repo_write(resolved):
            try:
                rel = resolved.relative_to(PROJECT_ROOT.resolve())
            except ValueError:
                rel = Path(resolved.name)
            redirected = tmp_path / "_hermetic_repo_writes" / rel
            redirected.parent.mkdir(parents=True, exist_ok=True)
            return redirected
        return target

    def _safe_write_text(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
        return orig_write_text(_redirect_target(self), data, *args, **kwargs)

    def _safe_write_bytes(self: Path, data: bytes, *args: Any, **kwargs: Any) -> int:
        return orig_write_bytes(_redirect_target(self), data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _safe_write_text)
    monkeypatch.setattr(Path, "write_bytes", _safe_write_bytes)
