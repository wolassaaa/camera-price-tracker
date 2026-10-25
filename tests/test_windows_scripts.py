from pathlib import Path


def test_windows_task_script_prefers_project_virtual_environment() -> None:
    script = Path("scripts/Register-CameraPriceTrackerTask.ps1").read_text(encoding="utf-8")

    assert ".venv\\Scripts\\python.exe" in script
    assert "Test-Path -LiteralPath $VenvPython" in script
