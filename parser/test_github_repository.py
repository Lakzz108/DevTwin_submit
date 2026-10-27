import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from github_repository import (
    GitHubRepositoryError,
    fetch_public_repository,
    normalize_github_url,
)


class GitHubRepositoryTest(unittest.TestCase):
    def test_normalizes_public_repository_url(self):
        self.assertEqual(
            ("https://github.com/octocat/Hello-World.git", "octocat", "Hello-World"),
            normalize_github_url("https://github.com/octocat/Hello-World"),
        )
        self.assertEqual(
            "https://github.com/octocat/Hello-World.git",
            normalize_github_url("https://github.com/octocat/Hello-World.git")[0],
        )

    def test_rejects_non_github_and_extra_path_urls(self):
        for url in (
            "https://example.com/user/repo",
            "https://github.com/user/repo/tree/main",
            "https://user:password@github.com/user/repo",
            "git@github.com:user/repo.git",
        ):
            with self.subTest(url=url), self.assertRaises(GitHubRepositoryError):
                normalize_github_url(url)

    def test_clones_under_supplied_cache_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            def fake_git(command, timeout):
                Path(command[-1]).mkdir()
                (Path(command[-1]) / ".git").mkdir()

            with patch("github_repository._run_git", side_effect=fake_git) as run_git:
                path, name = fetch_public_repository(
                    "https://github.com/octocat/Hello-World",
                    cache_dir=temporary_directory,
                )

        self.assertTrue(path.name.startswith("octocat--Hello-World-"))
        self.assertEqual("octocat/Hello-World", name)
        self.assertEqual("clone", run_git.call_args.args[0][1])


if __name__ == "__main__":
    unittest.main()
