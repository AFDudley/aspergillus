"""Tests for aspergillus integration with the validation orchestrator.

These tests verify the _run_aspergillus_check function produces correct
ValidationResult objects by calling aspergillus CLI via subprocess.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The orchestrator lives in the d-c venv; add it to import path.
_DC_SITE = Path.home() / ".exophial/dc/venv/lib/python3.12/site-packages"
if str(_DC_SITE) not in sys.path:
    sys.path.insert(0, str(_DC_SITE))

from dagster_composable.utilities.validation_orchestrator.validation_orchestrator_impl import (  # noqa: E402
    _run_aspergillus_check,
)


class TestAspergilllusCleanFile:
    """Aspergillus check on clean code should pass."""

    CLEAN_CODE = (
        "def short() -> int:\n"
        "    assert True\n"
        "    assert True\n"
        "    return 1\n"
    )

    def test_status_passed(self) -> None:
        result = _run_aspergillus_check(self.CLEAN_CODE, "clean.py")
        assert result.status == "passed"

    def test_no_errors(self) -> None:
        result = _run_aspergillus_check(self.CLEAN_CODE, "clean.py")
        assert result.errors == []

    def test_tier_is_2(self) -> None:
        result = _run_aspergillus_check(self.CLEAN_CODE, "clean.py")
        assert result.tier == 2

    def test_technology_is_aspergillus(self) -> None:
        result = _run_aspergillus_check(self.CLEAN_CODE, "clean.py")
        assert result.technology == "aspergillus"


class TestAspergilllusLevel2Violation:
    """Level 2 violations should produce high severity errors."""

    # Triggers ASP203: Global mutable state
    VIOLATING_CODE = "CACHE = {}\n"

    def test_status_failed(self) -> None:
        result = _run_aspergillus_check(self.VIOLATING_CODE, "bad.py")
        assert result.status == "failed"

    def test_has_errors(self) -> None:
        result = _run_aspergillus_check(self.VIOLATING_CODE, "bad.py")
        assert len(result.errors) >= 1

    def test_error_technology(self) -> None:
        result = _run_aspergillus_check(self.VIOLATING_CODE, "bad.py")
        assert result.errors[0].technology == "aspergillus"

    def test_error_code_is_asp203(self) -> None:
        result = _run_aspergillus_check(self.VIOLATING_CODE, "bad.py")
        assert result.errors[0].error_code == "ASP203"

    def test_severity_high(self) -> None:
        result = _run_aspergillus_check(self.VIOLATING_CODE, "bad.py")
        assert result.errors[0].severity == "high"

    def test_line_number_present(self) -> None:
        result = _run_aspergillus_check(self.VIOLATING_CODE, "bad.py")
        assert result.errors[0].line_number is not None
        assert result.errors[0].line_number >= 1

    def test_canonical_id_format(self) -> None:
        result = _run_aspergillus_check(self.VIOLATING_CODE, "bad.py")
        cid = result.errors[0].canonical_id
        assert cid.startswith("bad.py:")
        assert ":aspergillus:" in cid
        assert "ASP203" in cid


class TestAspergilllusLevel3Violation:
    """Level 3 violations should produce medium severity errors."""

    # Triggers ASP302: Optional return type
    OPTIONAL_CODE = (
        "def find(key: str) -> int | None:\n"
        "    assert isinstance(key, str)\n"
        "    assert len(key) > 0\n"
        "    return None\n"
    )

    def test_severity_medium(self) -> None:
        result = _run_aspergillus_check(self.OPTIONAL_CODE, "optional.py")
        asp302 = [e for e in result.errors if e.error_code == "ASP302"]
        assert len(asp302) >= 1
        assert asp302[0].severity == "medium"


class TestAspergilllusExecutionTime:
    """ValidationResult should have execution_time_ms."""

    def test_execution_time_present(self) -> None:
        result = _run_aspergillus_check("x = 1\n", "simple.py")
        assert result.execution_time_ms >= 0
