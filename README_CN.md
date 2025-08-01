# Claude Code 成本计算器

一个用于分析 Claude Code 使用历史的 Python 工具，计算跨项目和时间段的 Token 消耗和成本。

[English](README.md) | 中文

![Claude Code 成本计算器](screenshot_cn.png)

## 功能特性

- **多模型支持**: 支持 Claude Sonnet、Opus、Gemini 模型，提供精确定价
- **智能去重**: 智能重复检测，移除流式响应/重试机制产生的重复API记录
- **全面分析**: 每日使用趋势、项目排名、模型性能和成本分解
- **智能显示**: 自动隐藏空白部分，优化长项目路径显示
- **模型洞察**: 个别模型消耗跟踪和成本排名（使用2种以上模型时显示）
- **数据导出**: 支持 JSON 格式导出供进一步分析
- **时区处理**: 将 UTC 时间戳转换为本地时间，确保每日统计准确
- **国际化支持**: 自动检测系统语言，支持英文和中文

## 安装

### 一键安装（推荐）

```bash
# 自动检测系统最佳安装方式
curl -sSL https://raw.githubusercontent.com/keakon/claude-code-cost/main/install.sh | bash
```

### 方式 1：从 PyPI 安装（推荐）

#### 使用 uv（推荐 - 现代化且快速）
```bash
# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 作为全局工具安装
uv tool install claude-code-cost

# 运行命令
ccc
```

#### 使用 pipx（传统替代方案）
```bash
# 安装 pipx（如果尚未安装）
brew install pipx  # macOS
# 或者: python -m pip install --user pipx  # Linux/Windows

# 将 claude-code-cost 作为独立工具安装
pipx install claude-code-cost

# 现在可以在任何地方运行
ccc
```

#### 使用 pip 和虚拟环境
```bash
# 创建专用虚拟环境
python -m venv ~/.venvs/claude-cost
source ~/.venvs/claude-cost/bin/activate  # Linux/macOS
# 或者: ~/.venvs/claude-cost/Scripts/activate  # Windows

pip install claude-code-cost
ccc
```

### 方式 2：从源码安装

```bash
# 克隆仓库
git clone https://github.com/keakon/claude-code-cost.git
cd claude-code-cost

# 开发模式安装
uv pip install -e .

# 或使用 pip
pip install -e .
```

### 系统要求
- Python 3.8+
- 依赖库：`rich`、`pyyaml`

## 使用方法

### 基本用法

```bash
# 使用默认设置分析（从 PyPI 安装后）
ccc

# 或者从源码安装后
python main.py

# 指定自定义数据目录
ccc --data-dir /path/to/.claude/projects
```

### 高级选项

```bash
# 自定义显示限制
ccc --max-days 7 --max-projects 5

# 显示所有数据
ccc --max-days 0 --max-projects 0

# 以人民币显示成本
ccc --currency CNY

# 使用自定义汇率
ccc --currency CNY --usd-to-cny 7.3

# 导出到 JSON
ccc --export-json report.json

# 调试模式
ccc --log-level DEBUG

# 强制使用英文界面
ccc --language en

# 强制使用中文界面
ccc --language zh
```

## 输出部分

工具最多显示 5 个主要部分：

1. **总体统计**: 总项目数、Token 和成本
2. **今日使用**: 按项目显示当日消耗（仅在有活动时显示）
3. **每日统计**: 历史趋势（仅在存在历史数据时显示）
4. **项目排名**: 按成本排序的顶级项目
5. **模型统计**: 个别模型消耗和排名（使用2种以上模型时显示）

## 配置

该工具内置了所有支持模型的默认定价，但您可以通过创建用户配置文件来自定义定价。

### 自定义配置

在 `~/.claude-code-cost/model_pricing.yaml` 创建配置文件以覆盖默认设置：

```bash
# 创建配置目录
mkdir -p ~/.claude-code-cost

# 创建自定义配置
cat > ~/.claude-code-cost/model_pricing.yaml << 'EOF'
# 自定义模型定价配置
currency:
  usd_to_cny: 7.3        # 汇率
  display_unit: "USD"    # 默认显示货币

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
      - # >200K tokens
        input_per_million: 2.5
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
      - # >256K tokens
        input_per_million: 20.0
        output_per_million: 200.0
EOF
```

### 内置模型

工具包含以下模型的内置定价：
- **Claude 模型**: Sonnet、Opus
- **Gemini 模型**: 1.5-Pro、2.5-Pro（带阶梯定价）
- **Qwen 模型**: Qwen3-Coder（人民币定价和阶梯结构）

### 配置优先级

1. **内置默认**: 总是可用作为后备
2. **包配置**: 包含在软件包中
3. **用户配置**: `~/.claude-code-cost/model_pricing.yaml`（最高优先级）

## 命令行选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--data-dir` | `~/.claude/projects` | Claude 项目目录 |
| `--max-days` | `10` | 每日统计显示天数（0=全部） |
| `--max-projects` | `10` | 项目排名显示数量（0=全部） |
| `--currency` | `USD` | 显示货币单位（USD/CNY） |
| `--usd-to-cny` | `7.0` | 人民币转换汇率 |
| `--language` | `auto` | 界面语言（en/zh），自动检测 |
| `--log-level` | `WARNING` | 日志级别 |
| `--export-json` | - | 导出结果到 JSON 文件 |

## 数据来源

该工具分析 Claude 项目目录中的 JSONL 文件，通常位于：
- **macOS**: `~/.claude/projects`
- **Linux**: `~/.claude/projects`  
- **Windows**: `%USERPROFILE%\.claude\projects`

## 贡献

欢迎贡献！请随时提交 issue 和 pull request。

## 代码贡献

本项目约 99% 的代码由 [Claude Code](https://claude.ai/code) 生成。

## 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。