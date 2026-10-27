"""Fetch public GitHub repositories into DevTwin's ignored data directory."""

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_CACHE = PROJECT_ROOT / "data" / "repositories"
GITHUB_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class GitHubRepositoryError(ValueError):
    """A repository URL could not be validated or fetched safely."""


def normalize_github_url(value):
    """Accept only a public GitHub HTTPS repository URL."""

    if not isinstance(value, str) or not value.strip():
        raise GitHubRepositoryError("Enter a public GitHub repository URL.")

    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.port is not None
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise GitHubRepositoryError(
            "Use a public GitHub URL such as https://github.com/owner/repository."
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise GitHubRepositoryError(
            "Use a repository URL with an owner and repository name."
        )
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not all(GITHUB_NAME.fullmatch(part) for part in (owner, repository)):
        raise GitHubRepositoryError("The GitHub owner or repository name is invalid.")

    return f"https://github.com/{owner}/{repository}.git", owner, repository


def fetch_public_repository(github_url, cache_dir=None, timeout=180, refresh=True):
    """Clone a public repository or refresh its existing DevTwin clone."""

    normalized_url, owner, repository = normalize_github_url(github_url)
    cache_root = Path(cache_dir) if cache_dir else REPOSITORY_CACHE
    url_digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:10]
    destination = cache_root / f"{owner}--{repository}-{url_digest}"
    cache_root.mkdir(parents=True, exist_ok=True)

    if (destination / ".git").is_dir():
        origin = _git_output(["git", "-C", str(destination), "remote", "get-url", "origin"])
        if _canonical_remote(origin) != _canonical_remote(normalized_url):
            raise GitHubRepositoryError(
                "The saved repository checkout does not match this GitHub URL."
            )
        if not refresh:
            return destination.resolve(), f"{owner}/{repository}"
        try:
            _run_git(
                ["git", "-C", str(destination), "fetch", "--depth", "1", "origin"],
                timeout,
            )
            _run_git(["git", "-C", str(destination), "reset", "--hard", "FETCH_HEAD"], timeout)
        except GitHubRepositoryError as error:
            if "timed out" in str(error).lower():
                raise GitHubRepositoryError(
                    "GitHub did not respond in time. Check your connection and retry."
                ) from error
            raise GitHubRepositoryError(
                "DevTwin could not update this public GitHub repository. Check your "
                "connection and repository access, then retry."
            ) from error
        return destination.resolve(), f"{owner}/{repository}"

    if destination.exists():
        raise GitHubRepositoryError(
            "DevTwin's saved checkout is incomplete. Remove that checkout from "
            "the DevTwin data/repositories folder and retry."
        )

    try:
        _run_git(
            ["git", "clone", "--depth", "1", "--single-branch", normalized_url, str(destination)],
            timeout,
        )
    except GitHubRepositoryError as error:
        if destination.exists():
            shutil.rmtree(destination)
        message = str(error)
        if "timed out" in message.lower():
            raise GitHubRepositoryError(
                "GitHub did not respond in time. Check your connection and retry."
            ) from error
        raise GitHubRepositoryError(
            "DevTwin could not clone this repository. Check that the URL is a "
            "public GitHub repository and try again."
        ) from error

    return destination.resolve(), f"{owner}/{repository}"


def _canonical_remote(value):
    return value.strip().removesuffix(".git").rstrip("/").lower()


def _git_output(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise GitHubRepositoryError("DevTwin could not read the saved repository checkout.")
    return result.stdout.strip()


def _run_git(command, timeout):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GitHubRepositoryError("GitHub clone or fetch timed out.") from error
    except OSError as error:
        raise GitHubRepositoryError("Git is not available. Install Git and try again.") from error

    if result.returncode != 0:
        # Keep the raw Git output in backend logs only. It may include private
        # remote details and is not suitable for returning to the browser.
        raise GitHubRepositoryError(result.stderr.strip() or "Git operation failed.")
