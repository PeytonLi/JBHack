from __future__ import annotations

import sys
import textwrap

import pytest

from src.sandbox_runner import run_sandbox_test


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Sandbox subprocess test is flaky on Windows CI; covered on POSIX.",
)


ORIGINAL = textwrap.dedent(
    """
    WAREHOUSES = {1: "A", 2: "B"}

    def lookup(warehouse_id):
        return WAREHOUSES[warehouse_id]
    """
).strip() + "\n"


PATCHED = textwrap.dedent(
    """
    WAREHOUSES = {1: "A", 2: "B"}

    def lookup(warehouse_id):
        if warehouse_id not in WAREHOUSES:
            return None
        return WAREHOUSES[warehouse_id]
    """
).strip() + "\n"


TEST_CODE = textwrap.dedent(
    """
    import pytest

    from apps.target.src.main import lookup


    def test_lookup_returns_none_for_unknown():
        assert lookup(999) is None
    """
).strip() + "\n"


@pytest.mark.asyncio
async def test_sandbox_detects_repro_and_fix(tmp_path) -> None:
    result = await run_sandbox_test(
        original_content=ORIGINAL,
        patched_content=PATCHED,
        repo_relative_path="apps/target/src/main.py",
        test_code=TEST_CODE,
        timeout_s=30.0,
    )
    assert result.reproduced_bug is True
    assert result.fix_passes is True
    assert result.timed_out is False


MALFORMED_TEST = "def not a test"


@pytest.mark.asyncio
async def test_sandbox_treats_collection_error_as_not_reproduced(tmp_path) -> None:
    result = await run_sandbox_test(
        original_content=ORIGINAL,
        patched_content=PATCHED,
        repo_relative_path="apps/target/src/main.py",
        test_code=MALFORMED_TEST,
        timeout_s=20.0,
    )
    assert result.reproduced_bug is False


NO_TEST_FUNCTIONS = "x = 1\n"


@pytest.mark.asyncio
async def test_sandbox_no_tests_collected_is_not_reproduced(tmp_path) -> None:
    result = await run_sandbox_test(
        original_content=ORIGINAL,
        patched_content=PATCHED,
        repo_relative_path="apps/target/src/main.py",
        test_code=NO_TEST_FUNCTIONS,
        timeout_s=20.0,
    )
    assert result.reproduced_bug is False
    assert result.fix_passes is False


HANGING_TEST = textwrap.dedent(
    """
    import time

    def test_hangs():
        time.sleep(120)
    """
).strip() + "\n"


@pytest.mark.asyncio
async def test_sandbox_timeout_marks_result(tmp_path) -> None:
    result = await run_sandbox_test(
        original_content=ORIGINAL,
        patched_content=PATCHED,
        repo_relative_path="apps/target/src/main.py",
        test_code=HANGING_TEST,
        timeout_s=1.5,
    )
    assert result.timed_out is True
    assert result.reproduced_bug is False
    assert result.fix_passes is False
