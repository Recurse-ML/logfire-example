import logfire
import subprocess
import os
from pathlib import Path


def get_git_revision() -> str:
    """Get the current git commit hash."""
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
    logfire.configure(
        code_source=logfire.CodeSource(
            repository=get_git_repository(),
            revision=get_git_revision(),
            root_path="",
        )
    ) 