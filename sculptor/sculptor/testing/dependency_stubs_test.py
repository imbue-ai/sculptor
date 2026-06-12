import subprocess
from pathlib import Path

from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.testing.dependency_stubs import install_default_pi_stub


def test_install_default_pi_stub_writes_executable(tmp_path: Path) -> None:
    stub_path = install_default_pi_stub(tmp_path)

    assert stub_path == tmp_path / "pi"
    assert stub_path.is_file()
    assert stub_path.stat().st_mode & 0o111


def test_default_pi_stub_reports_pinned_version(tmp_path: Path) -> None:
    stub_path = install_default_pi_stub(tmp_path)

    result = subprocess.run([str(stub_path), "--version"], capture_output=True, text=True, check=False)

    assert result.returncode == 0
    # Real pi emits its version to stderr; the stub mirrors that.
    assert PI_VERSION_RANGE.recommended_version in result.stderr


def test_default_pi_stub_errors_on_other_invocations(tmp_path: Path) -> None:
    stub_path = install_default_pi_stub(tmp_path)

    result = subprocess.run([str(stub_path), "--mode", "rpc"], capture_output=True, text=True, check=False)

    assert result.returncode != 0
    assert "stub" in result.stderr.lower()
