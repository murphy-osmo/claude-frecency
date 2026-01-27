#!/usr/bin/env python3
"""Frecency-based file suggestions for Claude Code."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

DB_PATH = Path.home() / ".claude" / "file-frecency.tsv"
MAX_RESULTS = 15


def recency_multiplier(last_access: float) -> float:
    """Calculate recency multiplier based on last access time."""
    age_hours = (time.time() - last_access) / 3600
    if age_hours < 1:
        return 4.0
    elif age_hours < 24:
        return 2.0
    elif age_hours < 168:  # 1 week
        return 0.5
    else:
        return 0.25


def load_and_score() -> list[tuple[str, float]]:
    """Load database and compute frecency scores."""
    if not DB_PATH.exists():
        return []
    results = []
    for line in DB_PATH.read_text().strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            path, score, last_access = parts[0], float(parts[1]), float(parts[2])
            frecency = score * recency_multiplier(last_access)
            results.append((path, frecency))
    return results


def find_project_files(project_dir: str, query: str, limit: int) -> list[str]:
    """Find files in project matching query using git ls-files or find."""
    if limit <= 0:
        return []

    try:
        # Try git ls-files first (faster, respects .gitignore)
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            files = result.stdout.strip().split("\n")
        else:
            raise subprocess.SubprocessError("git failed")
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, FileNotFoundError):
        # Fallback to find
        try:
            result = subprocess.run(
                ["find", ".", "-type", "f", "-not", "-path", "./.git/*"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=2,
            )
            files = [f.lstrip("./") for f in result.stdout.strip().split("\n")]
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, FileNotFoundError):
            return []

    # Filter by query
    if query:
        files = [f for f in files if query in f.lower()]

    return files[:limit]


def main():
    data = json.load(sys.stdin)
    query = data.get("query", "").lower()
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    scored = load_and_score()

    # Filter to files within project directory
    scored = [(p, s) for p, s in scored if p.startswith(project_dir + "/")]

    # Filter by query (substring match)
    if query:
        scored = [(p, s) for p, s in scored if query in p.lower()]

    # Sort by frecency score descending
    scored.sort(key=lambda x: -x[1])

    # Convert to relative paths if within project
    frecency_results = []
    frecency_absolute = set()
    for path, _ in scored[:MAX_RESULTS]:
        frecency_absolute.add(path)
        if path.startswith(project_dir + "/"):
            frecency_results.append(path[len(project_dir) + 1 :])
        else:
            frecency_results.append(path)

    # Fill remaining slots with project files
    remaining = MAX_RESULTS - len(frecency_results)
    if remaining > 0:
        # Get more than needed to account for duplicates
        project_files = find_project_files(project_dir, query, remaining + len(frecency_results))
        for f in project_files:
            if len(frecency_results) >= MAX_RESULTS:
                break
            abs_path = os.path.join(project_dir, f)
            if abs_path not in frecency_absolute and f not in frecency_results:
                frecency_results.append(f)

    print("\n".join(frecency_results))


if __name__ == "__main__":
    main()
