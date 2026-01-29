# Claude Frecency

Frecency-based file suggestions for Claude Code. Ranks files by frequency + recency.

## Components

### frecency_track.py

Tracks file access via Claude Code hooks:
- `@file` references in prompts
- Write/Edit tool modifications
- Bash executions (python, node, pytest, scripts)

Data stored in `~/.claude/file-frecency.tsv`.

### file_suggestion.py

Returns up to 15 suggestions based on:
- **Frecency scores**: recency multipliers (4x last hour, 2x last day, 0.5x last week, 0.25x older)
- **Proximity**: +2 points per shared directory level with 5 most recent files
- **Directories**: immediate parents included, scored by median of contents, suffixed with `/`

Query modes:
- **Path prefix** (`src/sandbox/mu`): tab completion, shortest match first, directories preferred
- **Substring** (`train`): frecency-ranked matches

Falls back to `git ls-files` when frecency data is exhausted.

## Installation

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "python3 /path/to/frecency_track.py"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [{"type": "command", "command": "python3 /path/to/frecency_track.py"}]
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

Tab-separated: `path`, `score`, `last_access_timestamp`

```
/path/to/file.py	42.5	1706123456
```
