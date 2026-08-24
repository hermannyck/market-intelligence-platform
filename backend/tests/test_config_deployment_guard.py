"""Deployment-safety guard added when preparing this project for public hosting: refuses to
start with APP_ENV=production while JWT_SECRET is still the dev default. Run as a subprocess,
not a direct import, because the guard fires as a module-level side effect at import time --
`app.config` is already imported (with development settings) by the time any test module runs,
so `importlib.reload` in-process would leave stale state in every other already-imported module
that cached `SETTINGS` at import time.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _run(env_overrides: dict[str, str], code: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=30
    )


def test_production_with_default_jwt_secret_refuses_to_start():
    result = _run({"APP_ENV": "production", "DATABASE_URL": "sqlite:///:memory:"}, "import app.config")
    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr


def test_production_with_real_jwt_secret_starts_fine():
    result = _run(
        {"APP_ENV": "production", "JWT_SECRET": "a-real-random-secret", "DATABASE_URL": "sqlite:///:memory:"},
        "import app.config",
    )
    assert result.returncode == 0, result.stderr


def test_development_with_default_jwt_secret_still_starts_fine():
    # The dev-default secret is fine for local development -- only production is refused.
    result = _run({"DATABASE_URL": "sqlite:///:memory:"}, "import app.config")
    assert result.returncode == 0, result.stderr


def test_cors_allowed_origins_parses_comma_separated_env_var():
    result = _run(
        {
            "DATABASE_URL": "sqlite:///:memory:",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com, https://app-preview.example.com",
        },
        "import app.config; print(app.config.SETTINGS.cors_allowed_origins)",
    )
    assert result.returncode == 0, result.stderr
    assert "https://app.example.com" in result.stdout
    assert "https://app-preview.example.com" in result.stdout
