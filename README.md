# Claude Code Cost Calculator

A Python tool for analyzing Claude Code usage history, calculating token consumption and costs across projects and time periods.

English | [中文](README_CN.md)

![Claude Code Cost Calculator](screenshot.png)

## Features

- **Multi-model Support**: Claude Sonnet, Opus, Gemini models with accurate pricing
- **Advanced Deduplication**: Intelligent duplicate detection removes repeated API responses from streaming/retry mechanisms
- **Comprehensive Analytics**: Daily usage trends, project rankings, model performance, and cost breakdowns  
- **Smart Display**: Automatically hides empty sections and optimizes long project paths
- **Model Insights**: Individual model consumption tracking with cost ranking (shown when using 2+ models)
- **Data Export**: JSON export for further analysis
- **Time Zone Handling**: Converts UTC timestamps to local time for accurate daily statistics
- **Internationalization**: Auto-detects system language, supports English and Chinese (Simplified/Traditional)

## Installation

### Quick Install (One-liner)

```bash
# Auto-detect best installation method for your system
curl -sSL https://raw.githubusercontent.com/keakon/claude-code-cost/main/install.sh | bash
```

### Option 1: Install from PyPI (Recommended)

#### Using uv (Recommended - Modern & Fast)
```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install as a global tool
uv tool install claude-code-cost

# Run the command
ccc
```

#### Using pipx (Traditional alternative)
```bash
# Install pipx if you don't have it
brew install pipx  # macOS
# or: python -m pip install --user pipx  # Linux/Windows

# Install claude-code-cost as an isolated tool
pipx install claude-code-cost

# Now you can run from anywhere
ccc
```

#### Using pip with virtual environment
```bash
# Create a dedicated virtual environment
python -m venv ~/.venvs/claude-cost
source ~/.venvs/claude-cost/bin/activate  # Linux/macOS
# or: ~/.venvs/claude-cost/Scripts/activate  # Windows

pip install claude-code-cost
ccc
```

### Option 2: Install from Source

```bash
# Clone the repository
git clone https://github.com/keakon/claude-code-cost.git
cd claude-code-cost

# Install in development mode
uv pip install -e .

# Or using pip
pip install -e .
```

### Requirements
- Python 3.8+
- Dependencies: `rich`, `pyyaml`

## Usage

### Basic Usage

```bash
# Analyze with default settings (after installing from PyPI)
ccc

# Or if installed from source
python main.py

# Specify custom data directory
ccc --data-dir /path/to/.claude/projects
```

### Advanced Options

```bash
# Customize display limits
ccc --max-days 7 --max-projects 5

# Show all data
ccc --max-days 0 --max-projects 0

# Display costs in Chinese Yuan (CNY)
ccc --currency CNY

# Use custom exchange rate
ccc --currency CNY --usd-to-cny 7.3

# Export to JSON
ccc --export-json report.json

# Debug mode
ccc --log-level DEBUG

# Force English interface
ccc --language en

# Force Chinese interface
ccc --language zh
```

## Output Sections

The tool displays up to 5 main sections:

1. **Overall Statistics**: Total projects, tokens, and costs
2. **Today's Usage**: Current day consumption by project (shown only when active)
3. **Daily Statistics**: Historical trends (shown only when historical data exists)
4. **Project Rankings**: Top projects by cost
5. **Model Statistics**: Individual model consumption and ranking (shown when using 2+ models)

## Configuration

The tool comes with built-in default pricing for all supported models, but you can customize pricing by creating a user configuration file.

### Custom Configuration

Create a configuration file at `~/.claude-code-cost/model_pricing.yaml` to override default settings:

```bash
# Create config directory
mkdir -p ~/.claude-code-cost

# Create your custom configuration
cat > ~/.claude-code-cost/model_pricing.yaml << 'EOF'
# Custom model pricing configuration
currency:
  usd_to_cny: 7.3        # Exchange rate
  display_unit: "USD"    # Default display currency

pricing:
  sonnet:
    input_per_million: 3.0
    output_per_million: 15.0
    cache_read_per_million: 0.3
    cache_write_per_million: 3.75

  gemini-2.5-pro:
    # Multi-tier pricing example
    tiers:
      - threshold: 200000    # ≤200K tokens
        input_per_million: 1.25
        output_per_million: 10.0
      - # >200K tokens
        input_per_million: 2.5
        output_per_million: 15.0

  qwen3-coder:
    # CNY pricing example
    currency: "CNY"
    tiers:
      - threshold: 32000     # ≤32K tokens
        input_per_million: 4.0
        output_per_million: 16.0
      - threshold: 128000    # ≤128K tokens
        input_per_million: 6.0
        output_per_million: 24.0
      - threshold: 256000    # ≤256K tokens
        input_per_million: 10.0
        output_per_million: 40.0
      - # >256K tokens
        input_per_million: 20.0
        output_per_million: 200.0
EOF
```

### Built-in Models

The tool includes built-in pricing for:
- **Claude Models**: Sonnet, Opus
- **Gemini Models**: 1.5-Pro, 2.5-Pro (with tier pricing)
- **Qwen Models**: Qwen3-Coder (with CNY pricing and tier structure)

### Configuration Priority

1. **Built-in defaults**: Always available as fallback
2. **Package configuration**: Included with the package
3. **User configuration**: `~/.claude-code-cost/model_pricing.yaml` (highest priority)

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--data-dir` | `~/.claude/projects` | Claude projects directory |
| `--max-days` | `10` | Days to show in daily stats (0=all) |
| `--max-projects` | `10` | Projects to show in rankings (0=all) |
| `--currency` | `USD` | Display currency (USD/CNY) |
| `--usd-to-cny` | `7.0` | Exchange rate for CNY conversion |
| `--language` | `auto` | Interface language (en/zh), auto-detected |
| `--log-level` | `WARNING` | Logging level |
| `--export-json` | - | Export results to JSON file |

## Data Sources

The tool analyzes JSONL files in your Claude projects directory, typically located at:
- **macOS**: `~/.claude/projects`
- **Linux**: `~/.claude/projects`  
- **Windows**: `%USERPROFILE%\.claude\projects`

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## Code Attribution

Approximately 99% of this project's code was generated by [Claude Code](https://claude.ai/code).

## License

MIT License - see [LICENSE](LICENSE) file for details. 