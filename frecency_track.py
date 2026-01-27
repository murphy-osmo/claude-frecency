#!/usr/bin/env python3
"""Track file access frecency from Claude Code hooks."""

import json
import os
import re
import sys
import time
from pathlib import Path

DB_PATH = Path.home() / ".claude" / "file-frecency.tsv"
MAX_TOTAL_SCORE = 5000
DECAY_FACTOR = 0.9


def load_db() -> dict[str, tuple[float, float]]:
    """Load frecency database. Returns {path: (score, last_access)}."""
    if not DB_PATH.exists():
        return {}
    db = {}
    for line in DB_PATH.read_text().strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            db[parts[0]] = (float(parts[1]), float(parts[2]))
    return db


def save_db(db: dict[str, tuple[float, float]]) -> None:
    """Save frecency database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{path}\t{score}\t{ts}" for path, (score, ts) in db.items()]
    DB_PATH.write_text("\n".join(lines) + "\n" if lines else "")


def apply_decay(db: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """Apply decay when total score exceeds threshold."""
    total = sum(score for score, _ in db.values())
    if total > MAX_TOTAL_SCORE:
        db = {
            p: (s * DECAY_FACTOR, ts)
            for p, (s, ts) in db.items()
            if s * DECAY_FACTOR >= 1
        }
    return db


def increment_file(db: dict[str, tuple[float, float]], file_path: str) -> None:
    """Increment access count for a file."""
    now = time.time()
    current_score, _ = db.get(file_path, (0.0, now))
    db[file_path] = (current_score + 1, now)


def extract_at_references(prompt: str, cwd: str) -> list[str]:
    """Extract explicit @file references from user prompt."""
    # Match @path patterns (e.g., @src/main.py, @./config.yaml, @/absolute/path)
    pattern = r"@([^\s@]+)"
    paths = []
    for match in re.findall(pattern, prompt):
        # Resolve to absolute path
        if match.startswith("/"):
            candidate = match
        else:
            candidate = os.path.join(cwd, match)
        candidate = os.path.normpath(candidate)
        if os.path.isfile(candidate):
            paths.append(candidate)
    return paths


def main():
    data = json.load(sys.stdin)
    event = data.get("hook_event_name", "")
    cwd = data.get("cwd", os.getcwd())

    db = load_db()

    if event == "UserPromptSubmit":
        prompt = data.get("prompt", "")
        for path in extract_at_references(prompt, cwd):
            increment_file(db, path)

    elif event == "PostToolUse":
        tool = data.get("tool_name", "")
        if tool in ("Write", "Edit"):
            file_path = data.get("tool_input", {}).get("file_path", "")
            if file_path and os.path.isfile(file_path):
                increment_file(db, file_path)

    db = apply_decay(db)
    save_db(db)


if __name__ == "__main__":
    main()
