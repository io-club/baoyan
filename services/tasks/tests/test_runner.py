from pathlib import Path

import pytest

from app.runner import _safe_cwd


def test_task_cwd_inside_workspace(tmp_path: Path, monkeypatch) -> None:
    from app import config, runner

    monkeypatch.setattr(runner, "settings", config.Settings(
        database_url="unused",
        rabbitmq_url="unused",
        admin_password="unused",
        log_dir=str(tmp_path / "logs"),
        work_dir=str(tmp_path),
        poll_seconds=1,
        default_timezone="UTC",
    ))
    child = tmp_path / "project"
    assert _safe_cwd({"metadata": {"cwd": str(child)}}) == str(child.resolve())


def test_task_cwd_escape_is_rejected(tmp_path: Path, monkeypatch) -> None:
    from app import config, runner

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(runner, "settings", config.Settings(
        database_url="unused",
        rabbitmq_url="unused",
        admin_password="unused",
        log_dir=str(tmp_path / "logs"),
        work_dir=str(workspace),
        poll_seconds=1,
        default_timezone="UTC",
    ))
    with pytest.raises(ValueError):
        _safe_cwd({"metadata": {"cwd": str(tmp_path)}})

