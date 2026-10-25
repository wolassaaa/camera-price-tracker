from pathlib import Path


def test_docker_compose_keeps_config_writable_for_local_settings() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "./config:/app/config:ro" not in compose
    assert compose.count("./config:/app/config") == 2


def test_project_declares_dotenv_for_windows_env_example() -> None:
    project = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "python-dotenv" in project
