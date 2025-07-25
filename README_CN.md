# Claude 成本分析器

一个用于分析 Claude Code 使用成本的 Python 工具，可以计算跨项目和时间段的 Token 消耗和成本。

![Claude 成本分析器](screenshot.png)

[English](README.md) | 中文

## 功能特性

- **多模型支持**: 支持 Claude Sonnet、Opus、Gemini 模型，提供精确定价
- **全面分析**: 每日使用趋势、项目排名、模型性能和成本分解
- **智能显示**: 自动隐藏空白部分，优化长项目路径显示
- **模型洞察**: 个别模型消耗跟踪和成本排名（使用2种以上模型时显示）
- **数据导出**: 支持 JSON 格式导出供进一步分析
- **时区处理**: 将 UTC 时间戳转换为本地时间，确保每日统计准确

## 安装

### 系统要求
- Python 3.8+
- 依赖库: `rich`, `pyyaml`

### 快速安装

```bash
# 安装依赖
pip install rich pyyaml

# 或使用 uv（推荐）
uv pip install rich pyyaml
```

## 使用方法

### 基本用法

```bash
# 使用默认设置分析
python main.py

# 指定自定义数据目录
python main.py --data-dir /path/to/.claude/projects
```

### 高级选项

```bash
# 自定义显示限制
python main.py --max-days 7 --max-projects 5

# 显示所有数据
python main.py --max-days 0 --max-projects 0

# 以人民币显示成本
python main.py --currency CNY

# 使用自定义汇率
python main.py --currency CNY --usd-to-cny 7.3

# 导出到 JSON
python main.py --export-json report.json

# 调试模式
python main.py --log-level DEBUG
```

## 输出部分

工具最多显示 5 个主要部分：

1. **总体统计**: 总项目数、Token 和成本
2. **今日使用**: 按项目显示当日消耗（仅在有活动时显示）
3. **每日统计**: 历史趋势（仅在存在历史数据时显示）
4. **项目排名**: 按成本排序的顶级项目
5. **模型统计**: 个别模型消耗和排名（使用2种以上模型时显示）

## 模型定价

在 `model_pricing.yaml` 中配置模型定价：

```yaml
pricing:
  sonnet:
    input_per_million: 3.0
    output_per_million: 15.0
    cache_read_per_million: 0.3
    cache_write_per_million: 3.75

  gemini-2.5-pro:
    # 多级定价示例
    tiers:
      - threshold: 200000    # ≤200K tokens
        input_per_million: 1.25
        output_per_million: 10.0
      - # >200K tokens (无上限)
        input_per_million: 2.50
        output_per_million: 15.0

  qwen3-coder:
    # 人民币定价示例
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
      - # >256K tokens (无上限)
        input_per_million: 20.0
        output_per_million: 200.0

currency:
  usd_to_cny: 7.3
  display_unit: "USD"
```

## 命令行选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--data-dir` | `~/.claude/projects` | Claude 项目目录 |
| `--max-days` | `10` | 每日统计显示天数（0=全部） |
| `--max-projects` | `10` | 项目排名显示数量（0=全部） |
| `--currency` | `USD` | 显示货币单位（USD/CNY） |
| `--usd-to-cny` | `7.0` | 人民币转换汇率 |
| `--log-level` | `WARNING` | 日志级别 |
| `--export-json` | - | 导出结果到 JSON 文件 |

## 数据来源

该工具分析 Claude 项目目录中的 JSONL 文件，通常位于：
- **macOS**: `~/.claude/projects`
- **Linux**: `~/.claude/projects`  
- **Windows**: `%USERPROFILE%\.claude\projects`

## 贡献

欢迎贡献！请随时提交 issue 和 pull request。

## 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。