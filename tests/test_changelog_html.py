"""Drift guard: ``docs/html/changelog.html`` is generated from ``changelog.md`` by
``scripts/build-changelog-html.mjs``. If this fails after editing the changelog,
regenerate it with ``node scripts/build-changelog-html.mjs``."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-changelog-html.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to render the changelog")
def test_changelog_html_matches_a_fresh_render_of_changelog_md():
    result = subprocess.run(
        ["node", str(SCRIPT), "--check"], capture_output=True, text=True, check=False, cwd=ROOT
    )
    assert result.returncode == 0, result.stdout + result.stderr
