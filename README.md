# Claude Frecency

A frecency-based file suggestion system for Claude Code. Tracks file access patterns and suggests frequently-used files with recency weighting.

## What is Frecency?

Frecency combines **frequency** (how often) and **recency** (how recently) to rank items. Files you access frequently and recently score higher than files accessed long ago.

## Components

### frecency_track.py

A hook script that tracks file access from Claude Code:

- Monitors `@file` references in user prompts
- Tracks files modified via Write and Edit tools
- Tracks files executed via Bash (python, node, pytest, shell scripts, etc.)
- Stores data in `~/.claude/file-frecency.tsv`
- Implements score decay to prevent unbounded growth

### file_suggestion.py

Suggests files and directories based on frecency scores:

- Applies recency multipliers:
  - Last hour: 4x
  - Last 24 hours: 2x
  - Last week: 0.5x
  - Older: 0.25x
- Proximity scoring: boosts files near recently accessed files
  - Uses 5 most recent files as anchors
  - Adds 2 points per shared directory level
- Includes immediate parent directories of tracked files
  - Directories scored by median of their contained files
  - Directories suffixed with `/` to distinguish from files
- Tab completion: shortest prefix-matched path boosted to first position
  - Directories preferred over files when both match
  - Mimics bash tab completion (e.g., `src/sandbox/mu` → `src/sandbox/murphy/`)
- Scopes results to current project only
- Falls back to `git ls-files` (or `find` for non-git repos) when frecency results are exhausted
- Supports query filtering via substring match
- Returns top 15 results

## Installation

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/frecency_track.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/frecency_track.py"
          }
        ]
      }
    ]
  },
  "fileSuggestion": {
    "type": "command",
    "command": "python3 /path/to/file_suggestion.py"
  }
}
```

## Data Format

The frecency database (`~/.claude/file-frecency.tsv`) uses tab-separated values:

```
/path/to/file.py	42.5	1706123456
```

Fields: `path`, `score`, `last_access_timestamp`

## Dependencies

Python 3.7+ with standard library only.
