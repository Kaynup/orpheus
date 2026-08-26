import subprocess
import sys


def test_ruff_linting():
    """
    Programmatically run Ruff during pytest to ensure code quality is maintained.
    Fails the test suite if Ruff detects any linting violations.
    """
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "app", "tests", "cli.py"],
        capture_output=True,
        text=True,
    )

    error_msg = (
        f"Ruff linting failed! Please run `make lint` to fix the following issues:\n\n{result.stdout}\n{result.stderr}"
    )
    assert result.returncode == 0, error_msg
