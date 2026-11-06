"""The rules, the simulated world and the requirements are each one file in two places: the tools' copy and
the verifier's copy must be the same bytes."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["rules.py", "world.py", "guide.py"])
def test_the_tools_and_the_verifier_share_the_file_byte_for_byte(name: str) -> None:
    assert (ROOT / "src" / "plugin" / name).read_bytes() == (ROOT / "verifier" / name).read_bytes()
