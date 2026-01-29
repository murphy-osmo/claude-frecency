#!/usr/bin/env python3
"""Frecency-based file suggestions for Claude Code."""

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

DB_PATH = Path.home() / ".claude" / "file-frecency.tsv"
MAX_RESULTS = 15
PROXIMITY_WEIGHT = 2.0  # Points per shared directory level
ANCHOR_COUNT = 5  # Number of recent files to use as anchors


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


def load_db() -> list[tuple[str, float, float]]:
    """Load database entries as (path, score, last_access) tuples."""
    if not DB_PATH.exists():
        return []
    results = []
    for line in DB_PATH.read_text().strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            path, score, last_access = parts[0], float(parts[1]), float(parts[2])
            results.append((path, score, last_access))
    return results


def compute_frecency(entries: list[tuple[str, float, float]]) -> list[tuple[str, float]]:
    """Compute frecency scores from raw entries."""
    return [(path, score * recency_multiplier(last_access)) for path, score, last_access in entries]


def get_recent_anchors(entries: list[tuple[str, float, float]], n: int) -> list[str]:
    """Get the N most recently accessed files as anchors."""
    sorted_by_recency = sorted(entries, key=lambda x: -x[2])  # Sort by last_access descending
    return [path for path, _, _ in sorted_by_recency[:n]]


def shared_directory_depth(path1: str, path2: str) -> int:
    """Count shared directory components from root."""
    parts1 = Path(path1).parent.parts
    parts2 = Path(path2).parent.parts
    shared = 0
    for p1, p2 in zip(parts1, parts2):
        if p1 == p2:
            shared += 1
        else:
            break
    return shared


def proximity_score(candidate: str, anchors: list[str]) -> int:
    """Return max shared directory depth across all anchors."""
    if not anchors:
        return 0
    return max(shared_directory_depth(candidate, anchor) for anchor in anchors)


def find_project_files(project_dir: str, query: str, limit: int) -> list[str]:
    """Find files and directories in project using git ls-files or find."""
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
        # Fallback to find (files and directories)
        try:
            result = subprocess.run(
                ["find", ".", "(", "-type", "f", "-o", "-type", "d", ")", "-not", "-path", "./.git/*", "-not", "-path", "./.git"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=2,
            )
            entries = [e.lstrip("./") for e in result.stdout.strip().split("\n") if e and e != "."]
            # Filter by query and return early for find fallback
            if query:
                entries = [e for e in entries if query in e.lower()]
            return entries[:limit]
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, FileNotFoundError):
            return []

    # Extract directories that contain tracked files
    directories = set()
    for f in files:
        path = Path(f)
        for parent in path.parents:
            if parent != Path("."):
                directories.add(str(parent))

    # Combine files and directories
    all_entries = files + sorted(directories)

    # Filter by query
    if query:
        all_entries = [e for e in all_entries if query in e.lower()]

    return all_entries[:limit]


def main():
    data = json.load(sys.stdin)
    query = data.get("query", "").lower()
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    raw_entries = load_db()

    # Filter to files within project directory
    project_entries = [(p, s, t) for p, s, t in raw_entries if p.startswith(project_dir + "/")]

    # Get recent anchors for proximity scoring (before query filtering)
    anchors = get_recent_anchors(project_entries, ANCHOR_COUNT)

    # Compute frecency scores
    scored = compute_frecency(project_entries)

    # Extract immediate parent directories, score = median of contained files
    dir_scores: dict[str, list[float]] = {}
    for path, score in scored:
        parent_str = str(Path(path).parent)
        if parent_str.startswith(project_dir + "/"):
            dir_scores.setdefault(parent_str, []).append(score)
    directories = set(dir_scores.keys())
    scored.extend((d, statistics.median(scores)) for d, scores in dir_scores.items())

    # Filter by query (substring match)
    if query:
        scored = [(p, s) for p, s in scored if query in p.lower()]

    # Add proximity boost to scores
    scored = [(p, frecency + PROXIMITY_WEIGHT * proximity_score(p, anchors)) for p, frecency in scored]

    # Sort by final score descending
    scored.sort(key=lambda x: -x[1])

    # Convert to relative paths if within project, suffix directories with /
    frecency_results = []
    frecency_absolute = set()
    for path, _ in scored[:MAX_RESULTS]:
        frecency_absolute.add(path)
        if path.startswith(project_dir + "/"):
            rel_path = path[len(project_dir) + 1:]
        else:
            rel_path = path
        if path in directories:
            rel_path += "/"
        frecency_results.append(rel_path)

    # Fill remaining slots with project files
    remaining = MAX_RESULTS - len(frecency_results)
    if remaining > 0:
        # Get more than needed to account for duplicates
        project_files = find_project_files(project_dir, query, remaining + len(frecency_results))
        for f in project_files:
            if len(frecency_results) >= MAX_RESULTS:
                break
            abs_path = os.path.join(project_dir, f)
            # Add / suffix for directories
            display_path = f + "/" if Path(abs_path).is_dir() else f
            if abs_path not in frecency_absolute and display_path not in frecency_results:
                frecency_results.append(display_path)

    # Boost shortest prefix-matched entry to first position for tab completion
    if query:
        # Find shortest matching path from filesystem (prefer directories)
        candidates = sorted(Path(project_dir).glob(query + "*"))
        dirs = [c for c in candidates if c.is_dir()]
        files = [c for c in candidates if c.is_file()]
        # Sort by path length to get shortest match
        dirs.sort(key=lambda p: len(str(p)))
        files.sort(key=lambda p: len(str(p)))
        match = (dirs or files or [None])[0]
        if match:
            rel_path = str(match.relative_to(project_dir))
            if match.is_dir():
                rel_path += "/"
            # Remove from current position if present, then insert at front
            if rel_path in frecency_results:
                frecency_results.remove(rel_path)
            frecency_results.insert(0, rel_path)
            if len(frecency_results) > MAX_RESULTS:
                frecency_results.pop()

    print("\n".join(frecency_results))


if __name__ == "__main__":
    main()
