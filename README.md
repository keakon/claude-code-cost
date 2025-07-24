# Claude Cost Analyzer

A Python tool for analyzing Claude Code usage history, calculating token consumption and costs across projects and time periods.

![Claude Cost Analyzer](screenshot.png)

## Features

- **Multi-model Support**: Claude Sonnet, Opus, Gemini models with accurate pricing
- **Comprehensive Analytics**: Daily usage trends, project rankings, and cost breakdowns  
- **Smart Display**: Automatically hides empty sections and optimizes long project paths
- **Data Export**: JSON export for further analysis
- **Time Zone Handling**: Converts UTC timestamps to local time for accurate daily statistics

## Installation

### Requirements
- Python 3.8+
- Dependencies: `rich`, `pyyaml`

### Quick Setup

```bash
# Install dependencies
pip install rich pyyaml

# Or using uv (recommended)
uv pip install rich pyyaml
```

## Usage

### Basic Usage

```bash
# Analyze with default settings
python main.py

# Specify custom data directory
python main.py --data-dir /path/to/.claude/projects
```

### Advanced Options

```bash
# Customize display limits
python main.py --max-days 7 --max-projects 5

# Show all data
python main.py --max-days 0 --max-projects 0

# Export to JSON
python main.py --export-json report.json

# Debug mode
python main.py --log-level DEBUG
```

## Output Sections

The tool displays up to 4 main sections:

1. **Overall Statistics**: Total projects, tokens, and costs
2. **Today's Usage**: Current day consumption by project (shown only when active)
3. **Daily Statistics**: Historical trends (shown only when historical data exists)
4. **Project Rankings**: Top projects by cost

## Model Pricing

Configure model pricing in `model_pricing.yaml`:

```yaml
pricing:
  sonnet:
    input_per_million: 3.0
    output_per_million: 15.0
    cache_read_per_million: 0.3
    cache_write_per_million: 3.75

  gemini-2.5-pro:
    # Tiered pricing example
    input_per_million_low: 1.25    # ≤200K tokens
    input_per_million_high: 2.50   # >200K tokens
    threshold: 200000
```

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--data-dir` | `~/.claude/projects` | Claude projects directory |
| `--max-days` | `10` | Days to show in daily stats (0=all) |
| `--max-projects` | `10` | Projects to show in rankings (0=all) |
| `--log-level` | `WARNING` | Logging level |
| `--export-json` | - | Export results to JSON file |

## Data Sources

The tool analyzes JSONL files in your Claude projects directory, typically located at:
- **macOS**: `~/.claude/projects`
- **Linux**: `~/.claude/projects`  
- **Windows**: `%USERPROFILE%\.claude\projects`

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## License

MIT License - see [LICENSE](LICENSE) file for details. 