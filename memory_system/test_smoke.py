from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = SKILL_ROOT.parent


def run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout, proc.stderr


def expect_json_output(stdout: str):
    lines = [line for line in stdout.splitlines() if line.strip()]
    for start in range(len(lines)):
        candidate = "\n".join(lines[start:])
        try:
            return json.loads(candidate)
        except Exception:
            continue
    raise AssertionError(f"No JSON payload found in output:\n{stdout}")


def test_module_search_json():
    code, stdout, stderr = run(
        [sys.executable, "-m", "memory_system.cli", "search", "测试文本", "--json"],
        SKILLS_ROOT,
    )
    assert code == 0, stderr or stdout
    payload = expect_json_output(stdout)
    assert isinstance(payload, list)



def test_script_search_json():
    code, stdout, stderr = run(
        [sys.executable, "cli.py", "search", "测试文本", "--json"],
        SKILL_ROOT,
    )
    assert code == 0, stderr or stdout
    payload = expect_json_output(stdout)
    assert isinstance(payload, list)



def test_module_pack_json():
    code, stdout, stderr = run(
        [sys.executable, "-m", "memory_system.cli", "pack", "测试文本", "--json"],
        SKILLS_ROOT,
    )
    assert code == 0, stderr or stdout
    payload = expect_json_output(stdout)
    assert isinstance(payload, dict)
    assert "context_items" in payload



def test_script_pack_json():
    code, stdout, stderr = run(
        [sys.executable, "cli.py", "pack", "测试文本", "--json"],
        SKILL_ROOT,
    )
    assert code == 0, stderr or stdout
    payload = expect_json_output(stdout)
    assert isinstance(payload, dict)
    assert "context_items" in payload
