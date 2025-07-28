import logfire
import logging
import subprocess
import os
from pathlib import Path


def get_git_revision() -> str:
    """Get the current git commit hash."""
    if os.environ.get("GIT_COMMIT") is not None:
        return os.environ["GIT_COMMIT"]

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def get_git_repository() -> str:
    """Get the git repository URL."""
    if os.environ.get("GIT_REPO_URL") is not None:
        return os.environ["GIT_REPO_URL"]

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "https://github.com/Recurse-ML/logfire-example"


def configure_logfire():
    """Configure logfire with CodeSource information."""
    logger = logging.getLogger("logfire_config")
    logger.warning(f"Configuring logfire with Code source {get_git_repository()} at revision {get_git_revision()}")
    logfire.configure(
        code_source=logfire.CodeSource(
            repository=get_git_repository(),
            revision=get_git_revision(),
            root_path="",
        )
    )
