"""Tests for aspergillus CLI entry point (__main__.py)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_cli(file_path: str) -> subprocess.CompletedProcess[str]:
    """Run aspergillus CLI on a file and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "aspergillus", file_path],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )


class TestCLICleanFile:
    """CLI on a clean file should exit 0 with empty JSON array."""

    def test_exit_code_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("def short() -> int:\n    assert True\n    assert True\n    return 1\n")
        result = _run_cli(str(f))
        assert result.returncode == 0

    def test_outputs_empty_json_array(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("def short() -> int:\n    assert True\n    assert True\n    return 1\n")
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        assert data == []


class TestCLIWithViolations:
    """CLI on a file with violations should exit 1 with structured JSON."""

    def _make_violating_file(self, tmp_path: Path) -> Path:
        """Create a file that triggers ASP203 (global mutable state)."""
        f = tmp_path / "bad.py"
        f.write_text("CACHE = {}\n")
        return f

    def test_exit_code_one(self, tmp_path: Path) -> None:
        f = self._make_violating_file(tmp_path)
        result = _run_cli(str(f))
        assert result.returncode == 1

    def test_outputs_json_array(self, tmp_path: Path) -> None:
        f = self._make_violating_file(tmp_path)
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_violation_has_required_fields(self, tmp_path: Path) -> None:
        f = self._make_violating_file(tmp_path)
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        violation = data[0]
        assert "file" in violation
        assert "line" in violation
        assert "rule" in violation
        assert "message" in violation
        assert "severity" in violation

    def test_rule_code_extracted(self, tmp_path: Path) -> None:
        f = self._make_violating_file(tmp_path)
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        violation = data[0]
        assert violation["rule"] == "ASP203"

    def test_severity_level2_is_high(self, tmp_path: Path) -> None:
        """Level 2 rules (ASP2xx) should have severity 'high'."""
        f = self._make_violating_file(tmp_path)
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        violation = data[0]
        assert violation["severity"] == "high"

    def test_file_path_matches(self, tmp_path: Path) -> None:
        f = self._make_violating_file(tmp_path)
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        assert data[0]["file"] == str(f)

    def test_line_number_present(self, tmp_path: Path) -> None:
        f = self._make_violating_file(tmp_path)
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        assert isinstance(data[0]["line"], int)
        assert data[0]["line"] >= 1


class TestCLILevel3Severity:
    """Level 3 rules (ASP3xx) should have severity 'medium'."""

    def test_severity_level3_is_medium(self, tmp_path: Path) -> None:
        f = tmp_path / "optional.py"
        f.write_text(
            "def find(key: str) -> int | None:\n"
            "    assert isinstance(key, str)\n"
            "    assert len(key) > 0\n"
            "    return None\n"
        )
        result = _run_cli(str(f))
        data = json.loads(result.stdout)
        asp302 = [v for v in data if v["rule"] == "ASP302"]
        assert len(asp302) >= 1
        assert asp302[0]["severity"] == "medium"


class TestCLIMissingFile:
    """CLI with nonexistent file should exit 2 with error on stderr."""

    def test_exit_code_two(self) -> None:
        result = _run_cli("/nonexistent/file.py")
        assert result.returncode == 2

    def test_error_on_stderr(self) -> None:
        result = _run_cli("/nonexistent/file.py")
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()
