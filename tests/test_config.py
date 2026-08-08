# -*- coding: utf-8 -*-
"""Basic config tests — no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fesbuk.config as config


def test_root_is_repo_root():
    assert (config.ROOT / ".env").exists() or (config.ROOT / "pyproject.toml").exists()


def test_venv_python_os_aware():
    if config.IS_WINDOWS:
        assert config.venv_python(r"C:\venv").endswith("Scripts\\python.exe")
    else:
        assert config.venv_python("/venv").endswith("bin/python")


def test_page_id_from_env():
    # .env exists on this machine with PAGE_ID; just verify the field is a string
    assert isinstance(config.PAGE_ID, str)
