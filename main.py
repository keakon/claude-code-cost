import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from rich import box
from rich.console import Console
from rich.table import Table

# 配置日志
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
console = Console()

DEFAULT_USD_TO_CNY = 7.0


@dataclass
class ProjectStats:
    """项目统计数据"""

    project_name: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_messages: int = 0
    total_cost: float = 0.0
    models_used: Dict[str, int] = field(default_factory=dict)
    first_message_date: Optional[str] = None
    last_message_date: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


@dataclass
class ModelStats:
    """模型统计数据"""

    model_name: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_messages: int = 0
    total_cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


@dataclass
class DailyStats:
    """每日统计数据"""

    date: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_messages: int = 0
    total_cost: float = 0.0
    models_used: Dict[str, int] = field(default_factory=dict)
    projects_active: int = 0
    project_breakdown: Dict[str, ProjectStats] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


def load_full_config(config_file: str = "model_pricing.yaml") -> Dict:
    """加载完整配置（包括定价和货币配置）"""
    try:
        config_path = Path(__file__).parent / config_file
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    return yaml.safe_load(f)
                else:
                    return json.load(f)
    except Exception:
        logging.warning(f"无法加载配置文件 {config_file}，使用默认配置", exc_info=True)

    return {
        "currency": {"usd_to_cny": DEFAULT_USD_TO_CNY, "display_unit": "USD"},
        "pricing": {
            "sonnet": {
                "input_per_million": 3.0,
                "output_per_million": 15.0,
                "cache_read_per_million": 0.3,
                "cache_write_per_million": 3.75,
            },
            "opus": {
                "input_per_million": 15.0,
                "output_per_million": 75.0,
                "cache_read_per_million": 1.5,
                "cache_write_per_million": 18.75,
            },
        },
    }


def load_model_pricing(config_file: str = "model_pricing.yaml") -> Dict:
    """加载模型定价配置（支持YAML和JSON格式）"""
    full_config = load_full_config(config_file)
    return full_config.get("pricing", {})


def load_currency_config(config_file: str = "model_pricing.yaml") -> Dict:
    """加载货币配置"""
    full_config = load_full_config(config_file)
    return full_config.get("currency", {"usd_to_cny": DEFAULT_USD_TO_CNY, "display_unit": "USD"})


def calculate_model_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    pricing_config: Optional[Dict] = None,
    model_config_cache: Optional[Dict[str, Dict]] = None,
    currency_config: Optional[Dict] = None,
) -> float:
    """
    计算指定模型的成本

    Args:
        model_name: 模型名称
        input_tokens: 输入Token数量
        output_tokens: 输出Token数量
        cache_read_tokens: 缓存读取Token数量
        cache_creation_tokens: 缓存创建Token数量
        pricing_config: 定价配置
        model_config_cache: 模型配置缓存

    Returns:
        计算出的成本（美元）
    """
    if not pricing_config:
        return 0.0

    # 使用缓存的模型配置
    if model_config_cache and model_name in model_config_cache:
        model_config = model_config_cache[model_name]
    else:
        # 查找模型配置，按照优先级匹配
        model_config = None

        # 1. 优先级1：精确匹配（名字完全相同）
        for config_key, config_value in pricing_config.items():
            if model_name.lower() == config_key.lower():
                model_config = config_value
                break

        # 2. 优先级2：从上到下，第一个包含该名字的
        if not model_config:
            for config_key, config_value in pricing_config.items():
                if config_key.lower() in model_name.lower():
                    model_config = config_value
                    break

        # 3. 优先级3：如果没有任何一个包含它，成本为0
        if not model_config:
            logger.debug(f"未找到模型 {model_name} 的定价配置，成本设为0")
            return 0.0

        # 缓存结果
        if model_config_cache is not None:
            model_config_cache[model_name] = model_config

    # 计算成本 - 支持多级定价和标准定价
    input_rate = 0
    output_rate = 0
    cache_read_rate = 0
    cache_write_rate = 0

    if "tiers" in model_config:
        # 多级定价逻辑 - 按threshold排序，找到适用的档位（上限方式）
        tiers = model_config.get("tiers", [])
        selected_tier = None

        # 排序：有threshold的在前，没有threshold的在最后
        def sort_key(tier):
            threshold = tier.get("threshold")
            if threshold is None:
                return float("inf")  # 没有threshold的排到最后
            elif threshold == "inf":
                return float("inf")
            return float(threshold)

        sorted_tiers = sorted(tiers, key=sort_key)

        # 找到第一个适用的档位（input_tokens <= threshold 或 没有threshold限制）
        for tier in sorted_tiers:
            threshold = tier.get("threshold")
            if threshold is None:  # 没有threshold限制，适用于所有情况
                selected_tier = tier
                break
            elif threshold == "inf" or input_tokens <= float(threshold):
                selected_tier = tier
                break

        # 如果没有找到适用档位，使用最后一个（通常是无threshold限制的档位）
        if selected_tier is None and sorted_tiers:
            selected_tier = sorted_tiers[-1]

        if selected_tier:
            input_rate = selected_tier.get("input_per_million", 0)
            output_rate = selected_tier.get("output_per_million", 0)
            cache_read_rate = selected_tier.get("cache_read_per_million", 0)
            cache_write_rate = selected_tier.get("cache_write_per_million", 0)
    else:
        # 标准定价
        input_rate = model_config.get("input_per_million", 0)
        output_rate = model_config.get("output_per_million", 0)
        cache_read_rate = model_config.get("cache_read_per_million", 0)
        cache_write_rate = model_config.get("cache_write_per_million", 0)

    # 计算各部分成本
    input_cost = (input_tokens / 1_000_000) * input_rate
    output_cost = (output_tokens / 1_000_000) * output_rate
    cache_read_cost = (cache_read_tokens / 1_000_000) * cache_read_rate
    cache_creation_cost = (cache_creation_tokens / 1_000_000) * cache_write_rate

    total_cost = input_cost + output_cost + cache_read_cost + cache_creation_cost

    # 处理模型特定货币：如果模型配置指定了货币，需要转换为美元
    model_currency = model_config.get("currency", "USD")
    if model_currency == "CNY" and currency_config:
        # 将人民币转换为美元作为内部统一计价单位
        exchange_rate = currency_config.get("usd_to_cny", DEFAULT_USD_TO_CNY)
        total_cost = total_cost / exchange_rate

    return total_cost


class ClaudeHistoryAnalyzer:
    """Claude历史记录分析器"""

    def __init__(self, base_dir: Path, currency_config: Optional[Dict] = None):
        self.base_dir = base_dir
        self.project_stats: Dict[str, ProjectStats] = {}
        self.daily_stats: Dict[str, DailyStats] = {}
        self.model_stats: Dict[str, ModelStats] = {}
        self.pricing_config = load_model_pricing()
        self.currency_config = currency_config or load_currency_config()
        self.model_config_cache: Dict[str, Dict] = {}  # 模型匹配缓存

    def _convert_currency(self, amount: float) -> float:
        """根据配置转换货币"""
        if self.currency_config.get("display_unit", "USD") == "CNY":
            return amount * self.currency_config.get("usd_to_cny", DEFAULT_USD_TO_CNY)
        return amount

    def _format_cost(self, cost: float) -> str:
        """格式化成本显示"""
        converted_cost = self._convert_currency(cost)
        currency_symbol = "¥" if self.currency_config.get("display_unit", "USD") == "CNY" else "$"
        return f"{currency_symbol}{converted_cost:.2f}"

    def analyze_directory(self, base_dir: Path) -> None:
        """分析指定目录及其子目录中的所有JSONL文件"""
        if not base_dir.exists():
            logger.error(f"目录不存在: {base_dir}")
            return

        logger.info(f"开始分析目录: {base_dir}")

        # 查找所有项目目录
        project_dirs = [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("-")]

        if not project_dirs:
            logger.warning(f"在 {base_dir} 中未找到任何项目目录")
            return

        total_files = 0
        total_messages = 0

        for project_dir in project_dirs:
            project_name = self._extract_project_name_from_dir(project_dir.name)

            # 分析项目目录
            files_processed, messages_processed = self._analyze_single_directory(project_dir, project_name)
            total_files += files_processed
            total_messages += messages_processed

        logger.info(f"分析完成: {len(project_dirs)} 个项目, {total_files} 个文件, {total_messages} 条消息")

        # 验证分析结果
        if not self.project_stats:
            logger.warning("未找到任何有效的项目数据")
        elif total_messages == 0:
            logger.warning("未找到任何有效的消息数据")
        else:
            logger.info(f"成功分析 {len(self.project_stats)} 个项目")

        # 分析完成后，设置活跃项目数
        for daily_stats in self.daily_stats.values():
            daily_stats.projects_active = len(daily_stats.project_breakdown)

    def _extract_project_name_from_dir(self, dir_name: str) -> str:
        """从目录名提取项目名称"""
        # 特殊处理claude projects目录
        if "claude" in dir_name.lower() and "projects" in dir_name.lower():
            return ".claude/projects"

        # 首先尝试从JSONL文件中读取真实的项目路径
        project_dir = self.base_dir / dir_name
        if project_dir.exists():
            for jsonl_file in project_dir.glob("*.jsonl"):
                try:
                    with open(jsonl_file, "r", encoding="utf-8") as f:
                        first_line = f.readline().strip()
                        if first_line:
                            data = json.loads(first_line)
                            if "cwd" in data:
                                cwd_path = data["cwd"]
                                # 提取项目名称 (路径的最后一部分)
                                project_name = Path(cwd_path).name
                                if project_name:
                                    return project_name
                except (json.JSONDecodeError, IOError, KeyError):
                    continue

        # 如果无法从JSONL文件获取，回退到原有逻辑
        # 目录名格式通常是 -Users-username-Workspace-projectname
        # 提取最后的项目名称部分
        if "-Workspace-" in dir_name:
            project_name = dir_name.split("-Workspace-", 1)[1]
            # 处理特殊的空项目名或横线项目名
            if not project_name or project_name in ["", "-----", "------"]:
                return "Workspace"

            # 优化路径显示：如果太长使用省略号，但保持最后段完整
            path_parts = project_name.replace("-", "/").split("/")
            if len(path_parts) > 3:
                return f"{path_parts[0]}/.../{path_parts[-1]}"
            else:
                return project_name.replace("-", "/")

        # 如果没有Workspace标识，提取用户名后的部分
        parts = dir_name.split("-")
        if len(parts) >= 3:  # -Users-username-...
            path_parts = parts[3:] if len(parts) > 3 else [parts[2]]
            if len(path_parts) > 3:
                return f"{path_parts[0]}/.../{path_parts[-1]}"
            else:
                return "/".join(path_parts)

        return dir_name.lstrip("-")

    def _analyze_single_directory(self, directory: Path, project_name: str) -> tuple[int, int]:
        """分析单个目录中的JSONL文件"""
        if project_name not in self.project_stats:
            self.project_stats[project_name] = ProjectStats(project_name=project_name)

        project_stats = self.project_stats[project_name]

        jsonl_files = list(directory.glob("*.jsonl"))
        if not jsonl_files:
            return 0, 0

        files_processed = 0
        messages_processed = 0

        for jsonl_file in jsonl_files:
            try:
                file_messages = self._process_jsonl_file(jsonl_file, project_stats)
                messages_processed += file_messages
                files_processed += 1
            except Exception:
                logger.exception(f"处理文件 {jsonl_file} 时出错")
                continue

        return files_processed, messages_processed

    def _process_jsonl_file(self, file_path: Path, project_stats: ProjectStats) -> int:
        """处理单个JSONL文件"""
        messages_processed = 0

        # 获取文件创建时间作为备用日期
        try:
            file_stat = file_path.stat()
            file_creation_time = datetime.fromtimestamp(file_stat.st_ctime)
            fallback_date = file_creation_time.strftime("%Y-%m-%d")
        except Exception:
            logger.exception(f"无法获取文件 {file_path} 的创建时间")
            fallback_date = "unknown"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        if self._process_message(data, project_stats, fallback_date):
                            messages_processed += 1
                    except Exception:
                        logger.exception(f"处理消息失败 {file_path}:{line_number}")
                        continue
        except Exception:
            logger.exception(f"读取文件失败 {file_path}")
            return 0

        if messages_processed > 0:
            logger.debug(f"文件 {file_path.name} 处理了 {messages_processed} 条消息")

        return messages_processed

    def _convert_utc_to_local(self, utc_timestamp_str: str) -> str:
        """将UTC时间戳转换为本地时区的日期字符串"""
        try:
            # 解析UTC时间戳
            utc_dt = datetime.fromisoformat(utc_timestamp_str.replace("Z", "+00:00"))
            # 转换为本地时区
            local_dt = utc_dt.astimezone()
            return local_dt.strftime("%Y-%m-%d")
        except Exception:
            logger.exception(f"时区转换失败: {utc_timestamp_str}")
            return "unknown"

    def _process_message(
        self, data: Dict[str, Any], project_stats: ProjectStats, fallback_date: str = "unknown"
    ) -> bool:
        """处理单条消息数据"""
        # 只处理assistant类型的消息
        if data.get("type") != "assistant":
            return False

        message = data.get("message", {})
        if not message:
            logger.debug("消息数据为空")
            return False

        usage = message.get("usage", {})
        if not usage:
            logger.debug("缺少usage信息")
            return False

        # 提取token使用信息
        try:
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
            cache_creation_tokens = int(usage.get("cache_creation_input_tokens") or 0)
        except (ValueError, TypeError):
            logger.warning(f"Token数量格式错误", exc_info=True)
            return False

        if input_tokens == 0 and output_tokens == 0:
            return False

        # 提取模型信息
        model_name = message.get("model", "unknown")
        if not model_name or model_name == "unknown":
            logger.debug("缺少模型信息")

        # 提取时间戳并转换为本地时区，失败时使用备用日期
        timestamp_str = data.get("timestamp", "")
        if timestamp_str:
            date_str = self._convert_utc_to_local(timestamp_str)
            if date_str == "unknown" and fallback_date != "unknown":
                logger.debug(f"使用文件创建时间作为日期: {fallback_date}")
                date_str = fallback_date
        else:
            logger.debug("缺少时间戳信息，使用备用日期")
            date_str = fallback_date

        # 计算该消息的成本
        try:
            message_cost = calculate_model_cost(
                model_name,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                self.pricing_config,
                self.model_config_cache,
                self.currency_config,
            )
        except Exception:
            logger.exception(f"计算成本时出错")
            message_cost = 0.0

        # 更新项目统计
        project_stats.total_input_tokens += input_tokens
        project_stats.total_output_tokens += output_tokens
        project_stats.total_cache_read_tokens += cache_read_tokens
        project_stats.total_cache_creation_tokens += cache_creation_tokens
        project_stats.total_messages += 1
        project_stats.total_cost += message_cost  # 直接累积成本

        # 更新模型使用统计
        if model_name in project_stats.models_used:
            project_stats.models_used[model_name] += 1
        else:
            project_stats.models_used[model_name] = 1

        # 更新日期范围
        if date_str != "unknown":
            if not project_stats.first_message_date or date_str < project_stats.first_message_date:
                project_stats.first_message_date = date_str
            if not project_stats.last_message_date or date_str > project_stats.last_message_date:
                project_stats.last_message_date = date_str

        # 更新每日统计
        if date_str not in self.daily_stats:
            self.daily_stats[date_str] = DailyStats(date=date_str)

        daily_stats = self.daily_stats[date_str]
        daily_stats.total_input_tokens += input_tokens
        daily_stats.total_output_tokens += output_tokens
        daily_stats.total_cache_read_tokens += cache_read_tokens
        daily_stats.total_cache_creation_tokens += cache_creation_tokens
        daily_stats.total_messages += 1
        daily_stats.total_cost += message_cost  # 直接累积成本

        # 更新每日模型使用统计
        if model_name in daily_stats.models_used:
            daily_stats.models_used[model_name] += 1
        else:
            daily_stats.models_used[model_name] = 1

        # 更新每日项目统计
        if project_stats.project_name not in daily_stats.project_breakdown:
            daily_stats.project_breakdown[project_stats.project_name] = ProjectStats(
                project_name=project_stats.project_name
            )

        daily_project_stats = daily_stats.project_breakdown[project_stats.project_name]
        daily_project_stats.total_input_tokens += input_tokens
        daily_project_stats.total_output_tokens += output_tokens
        daily_project_stats.total_cache_read_tokens += cache_read_tokens
        daily_project_stats.total_cache_creation_tokens += cache_creation_tokens
        daily_project_stats.total_messages += 1
        daily_project_stats.total_cost += message_cost  # 直接累积成本

        if model_name in daily_project_stats.models_used:
            daily_project_stats.models_used[model_name] += 1
        else:
            daily_project_stats.models_used[model_name] = 1

        # 更新模型统计
        if model_name not in self.model_stats:
            self.model_stats[model_name] = ModelStats(model_name=model_name)

        model_stats = self.model_stats[model_name]
        model_stats.total_input_tokens += input_tokens
        model_stats.total_output_tokens += output_tokens
        model_stats.total_cache_read_tokens += cache_read_tokens
        model_stats.total_cache_creation_tokens += cache_creation_tokens
        model_stats.total_messages += 1
        model_stats.total_cost += message_cost

        return True

    def _generate_rich_report(self, max_days=10, max_projects=10) -> None:
        """生成Rich格式的统计报告

        Args:
            max_days: 每日统计显示的最大天数，0表示全部
            max_projects: 项目统计显示的最大项目数，0表示全部
        """
        # 获取有效项目（排除空项目）
        valid_projects = [p for p in self.project_stats.values() if p.total_tokens > 0]

        if not valid_projects:
            console.print("[red]未找到任何有效的项目数据[/red]")
            return

        # 计算总体统计
        total_input_tokens = sum(p.total_input_tokens for p in valid_projects)
        total_output_tokens = sum(p.total_output_tokens for p in valid_projects)
        total_cache_read_tokens = sum(p.total_cache_read_tokens for p in valid_projects)
        total_cache_creation_tokens = sum(p.total_cache_creation_tokens for p in valid_projects)
        total_cost = sum(p.total_cost for p in valid_projects)
        total_messages = sum(p.total_messages for p in valid_projects)

        # 1. 总体统计摘要
        summary_table = Table(title="📊 总体统计", box=box.ROUNDED, show_header=True, header_style="bold cyan")
        summary_table.add_column("指标", style="cyan", no_wrap=True, width=20)
        summary_table.add_column("数值", style="yellow", justify="right", width=20)

        summary_table.add_row("有效项目数", f"{len(valid_projects)}")
        summary_table.add_row("输入Token", f"{total_input_tokens/1_000_000:.1f}M")
        summary_table.add_row("输出Token", f"{total_output_tokens/1_000_000:.1f}M")
        summary_table.add_row("缓存读取", f"{total_cache_read_tokens/1_000_000:.1f}M")
        summary_table.add_row("缓存创建", f"{total_cache_creation_tokens/1_000_000:.1f}M")
        summary_table.add_row("总成本", self._format_cost(total_cost))
        summary_table.add_row("总消息数", f"{total_messages:,}")

        console.print("\n")
        console.print(summary_table)

        # 3. 今日消耗统计表格（只在有Token开销时显示）
        today_str = date.today().isoformat()
        today_stats = self.daily_stats.get(today_str)
        if today_stats and today_stats.project_breakdown and today_stats.total_cost > 0:
            today_table = Table(
                title=f"📈 今日消耗统计 ({today_str})", box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            today_table.add_column("项目", style="cyan", no_wrap=False, max_width=35)
            today_table.add_column("输入Token", style="bright_blue", justify="right", min_width=8)
            today_table.add_column("输出Token", style="yellow", justify="right", min_width=8)
            today_table.add_column("缓存读取", style="magenta", justify="right", min_width=8)
            today_table.add_column("缓存创建", style="bright_magenta", justify="right", min_width=8)
            today_table.add_column("消息数", style="red", justify="right", min_width=6)
            today_table.add_column("成本", style="green", justify="right", min_width=8)

            # 按成本排序今日项目
            sorted_today_projects = sorted(
                today_stats.project_breakdown.values(), key=lambda x: x.total_cost, reverse=True
            )

            for project in sorted_today_projects:
                if project.total_tokens > 0:  # 只显示有Token使用的项目
                    today_table.add_row(
                        project.project_name,
                        self._format_number(project.total_input_tokens),
                        self._format_number(project.total_output_tokens),
                        self._format_number(project.total_cache_read_tokens),
                        self._format_number(project.total_cache_creation_tokens),
                        self._format_number(project.total_messages),
                        self._format_cost(project.total_cost),
                    )

            # 添加总计行
            today_table.add_section()
            today_table.add_row(
                "总计",
                self._format_number(today_stats.total_input_tokens),
                self._format_number(today_stats.total_output_tokens),
                self._format_number(today_stats.total_cache_read_tokens),
                self._format_number(today_stats.total_cache_creation_tokens),
                self._format_number(today_stats.total_messages),
                self._format_cost(today_stats.total_cost),
            )

            console.print("\n")
            console.print(today_table)

        # 4. 每日消耗统计（只显示有数据的日期，且需有今天以外的数据）
        valid_daily_stats = {k: v for k, v in self.daily_stats.items() if v.total_tokens > 0}
        today_str = date.today().isoformat()

        # 排除今天的数据，检查是否有历史数据
        historical_stats = {k: v for k, v in valid_daily_stats.items() if k != today_str}

        if historical_stats:
            title_suffix = f"(最近{max_days}天)" if max_days > 0 else "(全部)"
            daily_table = Table(
                title=f"📅 每日消耗统计 {title_suffix}", box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            daily_table.add_column("日期", style="cyan", justify="center", min_width=10)
            daily_table.add_column("输入Token", style="bright_blue", justify="right", min_width=8)
            daily_table.add_column("输出Token", style="yellow", justify="right", min_width=8)
            daily_table.add_column("缓存读取", style="magenta", justify="right", min_width=8)
            daily_table.add_column("缓存创建", style="bright_magenta", justify="right", min_width=8)
            daily_table.add_column("消息数", style="red", justify="right", min_width=6)
            daily_table.add_column("成本", style="green", justify="right", min_width=8)
            daily_table.add_column("活跃项目", style="orange3", justify="right", min_width=8)

            # 生成最近N天的日期列表（排除今天）
            today = date.today()

            if max_days > 0:
                # 生成最近max_days天的日期列表（从昨天开始）
                date_list = [(today - timedelta(days=i + 1)).isoformat() for i in range(max_days)]
                # 只保留有数据的日期
                date_list = [d for d in date_list if d in valid_daily_stats]
            else:
                # 显示所有有数据的历史日期
                date_list = sorted(historical_stats.keys(), reverse=True)

            for date_str in date_list:
                daily_stats = self.daily_stats[date_str]
                daily_table.add_row(
                    date_str,
                    self._format_number(daily_stats.total_input_tokens),
                    self._format_number(daily_stats.total_output_tokens),
                    self._format_number(daily_stats.total_cache_read_tokens),
                    self._format_number(daily_stats.total_cache_creation_tokens),
                    self._format_number(daily_stats.total_messages),
                    self._format_cost(daily_stats.total_cost),
                    str(daily_stats.projects_active),
                )

            console.print("\n")
            console.print(daily_table)

        # 5. 项目消耗统计表格（放在最后，只在有数据时显示）
        valid_projects = [p for p in self.project_stats.values() if p.total_tokens > 0]
        if valid_projects:
            title_suffix = f"(TOP {max_projects})" if max_projects > 0 else "(全部)"
            projects_table = Table(
                title=f"🏗️ 项目消耗统计 {title_suffix}", box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            projects_table.add_column("项目", style="cyan", no_wrap=False, max_width=35)
            projects_table.add_column("输入Token", style="bright_blue", justify="right", min_width=8)
            projects_table.add_column("输出Token", style="yellow", justify="right", min_width=8)
            projects_table.add_column("缓存读取", style="magenta", justify="right", min_width=8)
            projects_table.add_column("缓存创建", style="bright_magenta", justify="right", min_width=8)
            projects_table.add_column("消息数", style="red", justify="right", min_width=6)
            projects_table.add_column("成本", style="green", justify="right", min_width=8)

            # 按成本排序项目
            sorted_projects = sorted(valid_projects, key=lambda x: x.total_cost, reverse=True)
            # 限制显示项目数
            if max_projects > 0:
                sorted_projects = sorted_projects[:max_projects]

            for project in sorted_projects:
                projects_table.add_row(
                    project.project_name,
                    self._format_number(project.total_input_tokens),
                    self._format_number(project.total_output_tokens),
                    self._format_number(project.total_cache_read_tokens),
                    self._format_number(project.total_cache_creation_tokens),
                    self._format_number(project.total_messages),
                    self._format_cost(project.total_cost),
                )

            console.print("\n")
            console.print(projects_table)

        # 6. 模型消耗统计表格（只在有2种或以上模型时显示）
        valid_models = [m for m in self.model_stats.values() if m.total_tokens > 0]
        if len(valid_models) >= 2:
            models_table = Table(
                title="🤖 模型消耗统计", box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            models_table.add_column("模型", style="cyan", no_wrap=False, max_width=35)
            models_table.add_column("输入Token", style="bright_blue", justify="right", min_width=8)
            models_table.add_column("输出Token", style="yellow", justify="right", min_width=8)
            models_table.add_column("缓存读取", style="magenta", justify="right", min_width=8)
            models_table.add_column("缓存创建", style="bright_magenta", justify="right", min_width=8)
            models_table.add_column("消息数", style="red", justify="right", min_width=6)
            models_table.add_column("成本", style="green", justify="right", min_width=8)

            # 按成本排序模型
            sorted_models = sorted(valid_models, key=lambda x: x.total_cost, reverse=True)

            for model in sorted_models:
                models_table.add_row(
                    model.model_name,
                    self._format_number(model.total_input_tokens),
                    self._format_number(model.total_output_tokens),
                    self._format_number(model.total_cache_read_tokens),
                    self._format_number(model.total_cache_creation_tokens),
                    self._format_number(model.total_messages),
                    self._format_cost(model.total_cost),
                )

            console.print("\n")
            console.print(models_table)

    def _format_number(self, num: int) -> str:
        """格式化数字显示"""
        if num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        else:
            return str(num)

    def export_json(self, output_path: Path) -> None:
        """导出分析结果为JSON格式"""
        # 转换数据为可序列化格式
        export_data = {
            "analysis_timestamp": datetime.now().isoformat(),
            "project_stats": {},
            "daily_stats": {},
            "model_stats": {},
            "summary": {
                "total_projects": len(self.project_stats),
                "total_models": len(self.model_stats),
                "total_input_tokens": sum(p.total_input_tokens for p in self.project_stats.values()),
                "total_output_tokens": sum(p.total_output_tokens for p in self.project_stats.values()),
                "total_cache_read_tokens": sum(p.total_cache_read_tokens for p in self.project_stats.values()),
                "total_cache_creation_tokens": sum(p.total_cache_creation_tokens for p in self.project_stats.values()),
                "total_cost": sum(p.total_cost for p in self.project_stats.values()),
                "total_messages": sum(p.total_messages for p in self.project_stats.values()),
            },
        }

        # 转换项目统计
        for name, stats in self.project_stats.items():
            export_data["project_stats"][name] = {
                "project_name": stats.project_name,
                "total_input_tokens": stats.total_input_tokens,
                "total_output_tokens": stats.total_output_tokens,
                "total_cache_read_tokens": stats.total_cache_read_tokens,
                "total_cache_creation_tokens": stats.total_cache_creation_tokens,
                "total_messages": stats.total_messages,
                "total_cost": stats.total_cost,
                "models_used": dict(stats.models_used),
                "first_message_date": stats.first_message_date,
                "last_message_date": stats.last_message_date,
            }

        # 转换每日统计
        for date_str, stats in self.daily_stats.items():
            project_breakdown = {}
            for proj_name, proj_stats in stats.project_breakdown.items():
                project_breakdown[proj_name] = {
                    "total_input_tokens": proj_stats.total_input_tokens,
                    "total_output_tokens": proj_stats.total_output_tokens,
                    "total_cache_read_tokens": proj_stats.total_cache_read_tokens,
                    "total_cache_creation_tokens": proj_stats.total_cache_creation_tokens,
                    "total_messages": proj_stats.total_messages,
                    "total_cost": proj_stats.total_cost,
                    "models_used": dict(proj_stats.models_used),
                }

            export_data["daily_stats"][date_str] = {
                "date": stats.date,
                "total_input_tokens": stats.total_input_tokens,
                "total_output_tokens": stats.total_output_tokens,
                "total_cache_read_tokens": stats.total_cache_read_tokens,
                "total_cache_creation_tokens": stats.total_cache_creation_tokens,
                "total_messages": stats.total_messages,
                "total_cost": stats.total_cost,
                "models_used": dict(stats.models_used),
                "projects_active": stats.projects_active,
                "project_breakdown": project_breakdown,
            }

        # 转换模型统计
        for name, stats in self.model_stats.items():
            export_data["model_stats"][name] = {
                "model_name": stats.model_name,
                "total_input_tokens": stats.total_input_tokens,
                "total_output_tokens": stats.total_output_tokens,
                "total_cache_read_tokens": stats.total_cache_read_tokens,
                "total_cache_creation_tokens": stats.total_cache_creation_tokens,
                "total_messages": stats.total_messages,
                "total_cost": stats.total_cost,
            }

        # 写入JSON文件
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        logger.info(f"分析结果已导出到: {output_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Claude历史记录分析工具")
    parser.add_argument(
        "--data-dir", type=Path, default=Path.home() / ".claude" / "projects", help="Claude项目数据目录路径"
    )
    parser.add_argument("--export-json", type=Path, help="导出JSON格式的分析结果到指定文件")
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="WARNING", help="日志级别"
    )
    parser.add_argument("--max-days", type=int, default=10, help="每日统计显示的最大天数，0表示全部（默认：10）")
    parser.add_argument("--max-projects", type=int, default=10, help="项目统计显示的最大项目数，0表示全部（默认：10）")
    parser.add_argument(
        "--currency", choices=["USD", "CNY"], default=None, help="显示货币单位（USD或CNY），默认使用配置文件中的设置"
    )
    parser.add_argument("--usd-to-cny", type=float, default=None, help="美元到人民币的汇率，默认使用配置文件中的设置")

    args = parser.parse_args()

    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # 加载货币配置
    currency_config = load_currency_config()

    # 如果命令行参数指定了货币单位或汇率，则覆盖配置文件中的设置
    if args.currency is not None:
        currency_config["display_unit"] = args.currency
    if args.usd_to_cny is not None:
        currency_config["usd_to_cny"] = args.usd_to_cny

    # 创建分析器并运行分析
    analyzer = ClaudeHistoryAnalyzer(args.data_dir, currency_config)
    analyzer.analyze_directory(args.data_dir)

    # 生成报告
    analyzer._generate_rich_report(max_days=args.max_days, max_projects=args.max_projects)

    # 导出JSON（如果指定了输出路径）
    if args.export_json:
        analyzer.export_json(args.export_json)


if __name__ == "__main__":
    main()
