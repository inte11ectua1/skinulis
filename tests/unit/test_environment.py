"""Проверки реального окружения разработки, без кода приложения."""

import sys
from pathlib import Path


def test_python_matches_project_pin() -> None:
    """uv должен запускать тесты на закреплённой версии Python 3.12."""
    project_root = Path(__file__).resolve().parents[2]
    pinned_version = (project_root / ".python-version").read_text().strip()

    assert sys.version_info[:2] == (3, 12)
    assert sys.version.split()[0] == pinned_version


def test_python_uses_virtual_environment() -> None:
    """Разработка не должна устанавливать зависимости в системный Python."""
    assert sys.prefix != sys.base_prefix
