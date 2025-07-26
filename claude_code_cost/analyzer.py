"""
Claude历史记录分析器

从main.py提取的核心分析类，负责解析Claude项目数据并生成统计报告。
"""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from rich import box
from rich.console import Console
from rich.table import Table

from .billing import calculate_model_cost, load_currency_config, load_model_pricing
from .models import DailyStats, ModelStats, ProjectStats
from .i18n import get_i18n, t

# 配置日志
logger = logging.getLogger(__name__)
console = Console()

DEFAULT_USD_TO_CNY = 7.0


class ClaudeHistoryAnalyzer:
    """Claude历史记录分析器"""

    def __init__(self, base_dir: Path, currency_config: Optional[Dict] = None, language: str = None):
        self.base_dir = base_dir
        self.project_stats: Dict[str, ProjectStats] = {}
        self.daily_stats: Dict[str, DailyStats] = {}
        self.model_stats: Dict[str, ModelStats] = {}
        self.pricing_config = load_model_pricing()
        self.currency_config = currency_config or load_currency_config()
        self.model_config_cache: Dict[str, Dict] = {}  # 模型匹配缓存
        self.i18n = get_i18n(language)

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
            logger.error(self.i18n.t('directory_not_exist', path=base_dir))
            return

        logger.info(self.i18n.t('analysis_start', path=base_dir))

        # 查找所有项目目录
        project_dirs = [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("-")]

        if not project_dirs:
            logger.warning(self.i18n.t('no_project_dirs', path=base_dir))
            return

        total_files = 0
        total_messages = 0

        for project_dir in project_dirs:
            project_name = self._extract_project_name_from_dir(project_dir.name)

            # 分析项目目录
            files_processed, messages_processed = self._analyze_single_directory(project_dir, project_name)
            total_files += files_processed
            total_messages += messages_processed

        logger.info(self.i18n.t('analysis_complete', projects=len(project_dirs), files=total_files, messages=total_messages))

        # 验证分析结果
        if not self.project_stats:
            logger.warning(self.i18n.t('no_data_found'))
        elif total_messages == 0:
            logger.warning(self.i18n.t('no_messages_found'))
        else:
            logger.info(self.i18n.t('projects_analyzed', count=len(self.project_stats)))

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
                logger.exception(self.i18n.t('file_processing_error', path=jsonl_file))
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
            logger.exception(self.i18n.t('file_creation_time_error', path=file_path))
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
                        logger.exception(self.i18n.t('message_processing_error', path=file_path, line=line_number))
                        continue
        except Exception:
            logger.exception(self.i18n.t('file_read_error', path=file_path))
            return 0

        if messages_processed > 0:
            logger.debug(self.i18n.t('file_processed', filename=file_path.name, count=messages_processed))

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
            logger.exception(self.i18n.t('timezone_conversion_error', timestamp=utc_timestamp_str))
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
            logger.debug(self.i18n.t('empty_message_data'))
            return False

        usage = message.get("usage", {})
        if not usage:
            logger.debug(self.i18n.t('missing_usage_info'))
            return False

        # 提取token使用信息
        try:
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
            cache_creation_tokens = int(usage.get("cache_creation_input_tokens") or 0)
        except (ValueError, TypeError):
            logger.warning(self.i18n.t('token_format_error'), exc_info=True)
            return False

        if input_tokens == 0 and output_tokens == 0:
            return False

        # 提取模型信息
        model_name = message.get("model", "unknown")
        if not model_name or model_name == "unknown":
            logger.debug(self.i18n.t('missing_model_info'))

        # 提取时间戳并转换为本地时区，失败时使用备用日期
        timestamp_str = data.get("timestamp", "")
        if timestamp_str:
            date_str = self._convert_utc_to_local(timestamp_str)
            if date_str == "unknown" and fallback_date != "unknown":
                logger.debug(self.i18n.t('using_file_creation_time', date=fallback_date))
                date_str = fallback_date
        else:
            logger.debug(self.i18n.t('missing_timestamp_info'))
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
            logger.exception(self.i18n.t('cost_calculation_error'))
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
            console.print(f"[red]{self.i18n.t('no_data_found')}[/red]")
            return

        # 计算总体统计
        total_input_tokens = sum(p.total_input_tokens for p in valid_projects)
        total_output_tokens = sum(p.total_output_tokens for p in valid_projects)
        total_cache_read_tokens = sum(p.total_cache_read_tokens for p in valid_projects)
        total_cache_creation_tokens = sum(p.total_cache_creation_tokens for p in valid_projects)
        total_cost = sum(p.total_cost for p in valid_projects)
        total_messages = sum(p.total_messages for p in valid_projects)

        # 1. 总体统计摘要
        summary_table = Table(title=self.i18n.t('overall_stats'), box=box.ROUNDED, show_header=True, header_style="bold cyan")
        summary_table.add_column(self.i18n.t('metric'), style="cyan", no_wrap=True, width=20)
        summary_table.add_column(self.i18n.t('value'), style="yellow", justify="right", width=20)

        summary_table.add_row(self.i18n.t('valid_projects'), f"{len(valid_projects)}")
        summary_table.add_row(self.i18n.t('input_tokens'), f"{total_input_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t('output_tokens'), f"{total_output_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t('cache_read'), f"{total_cache_read_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t('cache_write'), f"{total_cache_creation_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t('total_cost'), self._format_cost(total_cost))
        summary_table.add_row(self.i18n.t('total_messages'), f"{total_messages:,}")

        console.print("\n")
        console.print(summary_table)

        # 3. 今日消耗统计表格（只在有Token开销时显示）
        today_str = date.today().isoformat()
        today_stats = self.daily_stats.get(today_str)
        if today_stats and today_stats.project_breakdown and today_stats.total_cost > 0:
            today_table = Table(
                title=f"{self.i18n.t('today_usage')} ({today_str})", box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            today_table.add_column(self.i18n.t('project'), style="cyan", no_wrap=False, max_width=35)
            today_table.add_column(self.i18n.t('input_tokens'), style="bright_blue", justify="right", min_width=8)
            today_table.add_column(self.i18n.t('output_tokens'), style="yellow", justify="right", min_width=8)
            today_table.add_column(self.i18n.t('cache_read'), style="magenta", justify="right", min_width=8)
            today_table.add_column(self.i18n.t('cache_write'), style="bright_magenta", justify="right", min_width=8)
            today_table.add_column(self.i18n.t('messages'), style="red", justify="right", min_width=6)
            today_table.add_column(self.i18n.t('cost'), style="green", justify="right", min_width=8)

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
                self.i18n.t('total'),
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
            title_suffix = f"({self.i18n.t('recent_days', days=max_days)})" if max_days > 0 else f"({self.i18n.t('all_data')})"
            daily_table = Table(
                title=f"{self.i18n.t('daily_stats')} {title_suffix}", box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            daily_table.add_column(self.i18n.t('date'), style="cyan", justify="center", min_width=10)
            daily_table.add_column(self.i18n.t('input_tokens'), style="bright_blue", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t('output_tokens'), style="yellow", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t('cache_read'), style="magenta", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t('cache_write'), style="bright_magenta", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t('messages'), style="red", justify="right", min_width=6)
            daily_table.add_column(self.i18n.t('cost'), style="green", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t('active_projects'), style="orange3", justify="right", min_width=8)

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
            title_suffix = f"({self.i18n.t('top_n', n=max_projects)})" if max_projects > 0 else f"({self.i18n.t('all_data')})"
            projects_table = Table(
                title=f"{self.i18n.t('project_stats')} {title_suffix}", box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            projects_table.add_column(self.i18n.t('project'), style="cyan", no_wrap=False, max_width=35)
            projects_table.add_column(self.i18n.t('input_tokens'), style="bright_blue", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t('output_tokens'), style="yellow", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t('cache_read'), style="magenta", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t('cache_write'), style="bright_magenta", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t('messages'), style="red", justify="right", min_width=6)
            projects_table.add_column(self.i18n.t('cost'), style="green", justify="right", min_width=8)

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
                title=self.i18n.t('model_stats'), box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            models_table.add_column(self.i18n.t('model'), style="cyan", no_wrap=False, max_width=35)
            models_table.add_column(self.i18n.t('input_tokens'), style="bright_blue", justify="right", min_width=8)
            models_table.add_column(self.i18n.t('output_tokens'), style="yellow", justify="right", min_width=8)
            models_table.add_column(self.i18n.t('cache_read'), style="magenta", justify="right", min_width=8)
            models_table.add_column(self.i18n.t('cache_write'), style="bright_magenta", justify="right", min_width=8)
            models_table.add_column(self.i18n.t('messages'), style="red", justify="right", min_width=6)
            models_table.add_column(self.i18n.t('cost'), style="green", justify="right", min_width=8)

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

        logger.info(self.i18n.t('json_exported', path=output_path))