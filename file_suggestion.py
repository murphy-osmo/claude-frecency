#!/usr/bin/env python3
"""Frecency-based file suggestions for Claude Code."""

import json
import os
import sys
import time
from pathlib import Path

DB_PATH = Path.home() / ".claude" / "file-frecency.tsv"


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


def main():
    data = json.load(sys.stdin)
    query = data.get("query", "").lower()
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    scored = load_and_score()

    # Filter by query (substring match)
    if query:
        scored = [(p, s) for p, s in scored if query in p.lower()]

    # Filter to files that still exist
    scored = [(p, s) for p, s in scored if os.path.isfile(p)]

    # Sort by frecency score descending
    scored.sort(key=lambda x: -x[1])

    # Convert to relative paths if within project
    results = []
    for path, _ in scored[:15]:
        if path.startswith(project_dir + "/"):
            results.append(path[len(project_dir) + 1 :])
        else:
            results.append(path)

    print("\n".join(results))


if __name__ == "__main__":
    main()
