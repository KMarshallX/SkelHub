"""Validate PR release choices and prepare checkbox-driven release metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib


CHOICES = {
    "bugfix / refactoring": "patch",
    "minor": "minor",
    "major": "major",
    "no release": "none",
}


def release_choice(body: str) -> str:
    """Read exactly one checked option in the PR's Version Choice section."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    body = re.sub(r"(?ms)^```.*?^```[^\n]*", "", body)
    sections = re.findall(
        r"(?ms)^## Version Choice\s*\n(.*?)(?=^## |\Z)", body
    )
    if len(sections) != 1:
        raise ValueError("PR must contain exactly one '## Version Choice' section.")
    selected = re.findall(r"(?m)^\s*- \[[xX]\]\s+(.+)$", sections[0])
    if len(selected) != 1:
        raise ValueError("Select exactly one version checkbox in the PR description.")
    match = re.match(r"`([^`]+)`(?:\s|$)", selected[0])
    if not match or match[1] not in CHOICES:
        raise ValueError("Unknown version choice; restore the PR template option text.")
    return CHOICES[match[1]]


def next_version(version: str, choice: str) -> str:
    """Increment a stable X.Y.Z version, resetting lower components."""
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError(f"Expected a stable X.Y.Z version, got {version!r}.")
    major, minor, patch = map(int, version.split("."))
    if choice == "major":
        return f"{major + 1}.0.0"
    if choice == "minor":
        return f"{major}.{minor + 1}.0"
    if choice == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if choice == "none":
        return version
    raise ValueError(f"Unknown release type: {choice!r}")


def project_version(text: str) -> str:
    """Read and validate the authoritative package version."""
    version = tomllib.loads(text)["project"]["version"]
    next_version(version, "none")
    return version


def replace_version(text: str, version: str) -> str:
    """Update only project.version, preserving the rest of the TOML file."""
    section = re.search(r"(?ms)^\[project\]\s*\n.*?(?=^\[|\Z)", text)
    if section is None:
        raise ValueError("Missing [project] section.")
    updated, count = re.subn(
        r"(?m)^(version\s*=\s*)[\"'][^\"']*[\"']",
        lambda match: f'{match[1]}"{version}"',
        section[0],
    )
    if count != 1:
        raise ValueError("Expected one project.version assignment.")
    result = text[:section.start()] + updated + text[section.end():]
    if project_version(result) != version:
        raise ValueError("Updated project version does not match the requested version.")
    return result


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def is_release_pr(pr: dict, repository: str) -> bool:
    """Only the repository's own dev -> main PRs can publish releases."""
    return (
        pr["head"]["ref"] == "dev"
        and pr["base"]["ref"] == "main"
        and pr["head"]["repo"]["full_name"] == repository
        and pr["base"]["repo"]["full_name"] == repository
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["check", "prepare"])
    args = parser.parse_args()
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    choice = release_choice(pr.get("body") or "")
    tracked_tests = git("ls-files", "tests")
    if tracked_tests:
        raise ValueError("Remove tracked test instances from this PR; tests remain local.")
    path = Path("pyproject.toml")
    text = path.read_text()
    current = project_version(text)
    eligible = is_release_pr(pr, os.environ["GITHUB_REPOSITORY"])
    if args.mode == "check":
        base = project_version(git("show", f'{pr["base"]["sha"]}:pyproject.toml'))
        if current != base:
            raise ValueError(
                f"Keep project.version at the base branch version ({base}); "
                "release automation applies the selected increment. "
                "Sync main back into dev after each release."
            )
        target = next_version(current, choice)
        message = (
            f"Selected {choice}: {current} -> {target}. "
            + ("Release eligible." if eligible else "This PR will not publish a release.")
        )
        print(message)
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a") as output:
                output.write(message + "\n")
        return
    if not eligible or not pr.get("merged") or event.get("action") != "closed":
        raise ValueError("Releases require a merged, same-repository dev -> main PR.")
    if git("rev-parse", "HEAD") != pr["merge_commit_sha"]:
        raise ValueError("Release checkout must match this PR's exact merge commit.")
    target = next_version(current, choice)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"release={'false' if choice == 'none' else 'true'}\n")
        output.write(f"version={target}\ntag=v{target}\n")
    if choice == "none":
        print("No release selected; leaving package version and tags unchanged.")
        return
    path.write_text(replace_version(text, target))
    notes = Path(os.environ["RUNNER_TEMP"]) / "skelhub-release-notes.md"
    notes.write_text(
        f'{pr["title"]} (#{pr["number"]})\n\n'
        f'{pr.get("body") or ""}\n\nSource: {pr["html_url"]}\n'
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
