"""验证进程入口的环境变量加载语义。"""

import os
from pathlib import Path

import pytest

from backend.config.env import load_env


def test_load_env_reads_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """文件中的变量会进入进程环境。"""
    env_file = tmp_path / ".env"
    env_file.write_text("TRIPWEAVE_TEST_ENV=from-file\n", encoding="utf-8")
    monkeypatch.delenv("TRIPWEAVE_TEST_ENV", raising=False)
    load_env(env_file)
    assert os.environ["TRIPWEAVE_TEST_ENV"] == "from-file"


def test_load_env_keeps_existing_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """已存在的环境变量优先于 .env 中的同名变量。"""
    env_file = tmp_path / ".env"
    env_file.write_text("TRIPWEAVE_TEST_ENV=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TRIPWEAVE_TEST_ENV", "existing")
    load_env(env_file)
    assert os.environ["TRIPWEAVE_TEST_ENV"] == "existing"
