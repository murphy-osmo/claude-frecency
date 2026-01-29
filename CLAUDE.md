# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a frecency-based file suggestion system for Claude Code. It consists of two Python scripts that work as Claude Code hooks:

1. **frecency_track.py** - Tracks file access via UserPromptSubmit (@file references) and PostToolUse (Write/Edit/Bash) hooks
2. **file_suggestion.py** - Provides file and directory suggestions based on frecency scores, used by Claude Code's fileSuggestion config

## Running

Both scripts read JSON from stdin and are invoked by Claude Code hooks:

```bash
# Test frecency tracking
echo '{"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": "/path/to/file"}, "cwd": "/project"}' | python3 frecency_track.py

# Test file suggestions
echo '{"query": ""}' | CLAUDE_PROJECT_DIR=/project python3 file_suggestion.py
```

## Architecture

- Data stored in `~/.claude/file-frecency.tsv` (tab-separated: path, score, timestamp)
- Scores decay by 0.9x when total exceeds 5000 to prevent unbounded growth
- Recency multipliers: 4x (last hour), 2x (last day), 0.5x (last week), 0.25x (older)
- Proximity scoring: files in same directory as recent anchors get +2 points per shared directory level
- Directory suggestions: immediate parent directories are included, scored by median of their contents
- Suggestion fallback: frecency results first, then `git ls-files` (or `find` if not a git repo)
- Project scoping via `CLAUDE_PROJECT_DIR` environment variable
