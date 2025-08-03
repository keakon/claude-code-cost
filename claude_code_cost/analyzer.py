"""Claude History Analyzer

Core analysis class for parsing Claude project data and generating statistical reports.
"""

import json
import logging
import platform
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from rich import box
from rich.console import Console
from rich.table import Table

from .billing import calculate_model_cost, load_currency_config, load_model_pricing
from .i18n import get_i18n
from .models import DailyStats, ModelStats, ProjectStats

# Configure logging
logger = logging.getLogger(__name__)

# Initialize console with Windows compatibility
if platform.system() == "Windows":
    # Use legacy Windows console mode to avoid encoding issues in CI
    console = Console(force_terminal=False, legacy_windows=True)
else:
    console = Console()

DEFAULT_USD_TO_CNY = 7.0


class ClaudeHistoryAnalyzer:
    """Analyzes Claude usage history from project files"""

    def __init__(self, base_dir: Path, currency_config: Optional[Dict] = None, language: Optional[str] = None):
        self.base_dir = base_dir
        self.project_stats: Dict[str, ProjectStats] = {}
        self.daily_stats: Dict[str, DailyStats] = {}
        self.model_stats: Dict[str, ModelStats] = {}
        self.pricing_config = load_model_pricing()
        self.currency_config = currency_config or load_currency_config()
        self.model_config_cache: Dict[str, Dict] = {}  # Cache for model configuration lookups
        self.i18n = get_i18n(language)

        # Validate and fix currency configuration
        self._validate_and_fix_currency_config()

        # Initialize a dict to accumulate tokens for streaming responses
        self._message_accumulator = {}  # message_id -> accumulated tokens
        self._counted_message_ids = set()  # Track which message IDs we've already counted for messages
        self._billed_message_ids = set()  # Track which message IDs we've already billed across all files
        self._session_continuation_mode = False  # Track if current file is in session continuation mode

    def _validate_and_fix_currency_config(self) -> None:
        """Validate currency configuration and apply default fallbacks if needed"""
        if not isinstance(self.currency_config, dict):
            logger.warning("Invalid currency config format, using defaults")
            self.currency_config = {"usd_to_cny": DEFAULT_USD_TO_CNY, "display_unit": "USD"}
            return

        # Validate and fix exchange rate
        usd_to_cny = self.currency_config.get("usd_to_cny", DEFAULT_USD_TO_CNY)
        if not isinstance(usd_to_cny, (int, float)) or usd_to_cny <= 0:
            logger.warning(f"Invalid USD to CNY rate: {usd_to_cny}, using default: {DEFAULT_USD_TO_CNY}")
            self.currency_config["usd_to_cny"] = DEFAULT_USD_TO_CNY

        # Validate display unit
        display_unit = self.currency_config.get("display_unit", "USD")
        if display_unit not in ["USD", "CNY"]:
            logger.warning(f"Invalid display unit: {display_unit}, using USD")
            self.currency_config["display_unit"] = "USD"

    def _convert_currency(self, amount: float) -> float:
        """Convert amount to display currency based on configuration"""
        if self.currency_config.get("display_unit", "USD") == "CNY":
            # Use pre-validated exchange rate from initialization
            return amount * self.currency_config["usd_to_cny"]
        return amount

    def _format_cost(self, cost: float) -> str:
        """Format cost for display with appropriate currency symbol"""
        converted_cost = self._convert_currency(cost)
        display_unit = self.currency_config.get("display_unit", "USD")

        # Use ASCII-compatible currency symbols on Windows to avoid encoding issues
        if platform.system() == "Windows":
            currency_symbol = "CNY" if display_unit == "CNY" else "USD"
            return f"{converted_cost:.2f} {currency_symbol}"
        else:
            currency_symbol = "¥" if display_unit == "CNY" else "$"
            return f"{currency_symbol}{converted_cost:.2f}"

    def analyze_directory(self, base_dir: Path) -> None:
        """Analyze all JSONL files in Claude projects directory structure

        Scans for project directories (starting with '-') and processes JSONL files
        containing Claude conversation history to extract token usage and costs.
        """
        if not base_dir.exists():
            logger.error(self.i18n.t("directory_not_exist", path=base_dir))
            return

        logger.info(self.i18n.t("analysis_start", path=base_dir))

        # Find project directories (Claude stores projects in dirs starting with '-')
        project_dirs = [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("-")]

        if not project_dirs:
            logger.warning(self.i18n.t("no_project_dirs", path=base_dir))
            return

        total_files = 0
        total_messages = 0

        for project_dir in project_dirs:
            project_name = self._extract_project_name_from_dir(project_dir.name)

            # Process each project directory for JSONL files
            files_processed, messages_processed = self._analyze_single_directory(project_dir, project_name)
            total_files += files_processed
            total_messages += messages_processed

        logger.info(
            self.i18n.t("analysis_complete", projects=len(project_dirs), files=total_files, messages=total_messages)
        )

        # Validate analysis results and log summary
        if not self.project_stats:
            logger.warning(self.i18n.t("no_data_found"))
        elif total_messages == 0:
            logger.warning(self.i18n.t("no_messages_found"))
        else:
            logger.info(self.i18n.t("projects_analyzed", count=len(self.project_stats)))

        # Set active project count for daily statistics
        for daily_stats in self.daily_stats.values():
            daily_stats.projects_active = len(daily_stats.project_breakdown)

    def _extract_project_name_from_dir(self, dir_name: str) -> str:
        """Extract readable project name from Claude's directory naming scheme

        Claude uses directory names like '-Users-username-path-to-projectname'
        This method extracts meaningful project names for display from various directory structures.
        """
        # Special handling for claude projects directory
        if "claude" in dir_name.lower() and "projects" in dir_name.lower():
            return ".claude/projects"

        # Try to read actual project path from JSONL files first (most accurate)
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
                                # Extract meaningful project path from the actual working directory
                                path = Path(cwd_path)

                                # Try to find a reasonable project path representation
                                # Look for common patterns like parent/child for better display
                                if len(path.parts) >= 2:
                                    # If the path is deep, show parent/current for context
                                    parent = path.parent.name
                                    current = path.name

                                    # Avoid showing generic parent names like "Users", "home", etc.
                                    if parent.lower() not in ["users", "home", "documents", "desktop"]:
                                        return f"{parent}/{current}"
                                    else:
                                        return current
                                else:
                                    return path.name
                except (json.JSONDecodeError, UnicodeDecodeError, IOError, OSError):
                    logger.exception(self.i18n.t("file_processing_error", path=jsonl_file))
                    continue

        # Fallback: Parse directory name using Claude's naming convention
        # Directory names are typically like: -Users-username-path-to-project-name
        # We want to extract the meaningful project path

        # Remove leading dash and split by dashes
        clean_name = dir_name.lstrip("-")
        parts = clean_name.split("-")

        # If we have enough parts, try to find a meaningful project path
        if len(parts) >= 3:
            # Skip the first few parts that are likely system paths (Users, username)
            # Look for common development directory indicators
            dev_indicators = ["workspace", "projects", "code", "dev", "repos", "src", "git", "documents"]
            project_start_idx = 2  # Default: skip Users and username

            # Try to find a better starting point based on common dev directory names
            for i, part in enumerate(parts):
                if part.lower() in dev_indicators and i < len(parts) - 1:
                    project_start_idx = i + 1
                    break

            # Extract the project path starting from the identified index
            project_parts = parts[project_start_idx:]

            if project_parts:
                # For long paths, abbreviate to keep display manageable
                if len(project_parts) > 3:
                    # Take first and last parts with abbreviation
                    first = project_parts[0]
                    last = project_parts[-1]
                    return f"{first}/.../{last}"
                elif len(project_parts) == 2:
                    # For two parts, show as directory/project
                    return "/".join(project_parts)
                else:
                    # Single part or short path, join with dashes
                    return "-".join(project_parts)

        # If we have fewer parts or can't parse meaningfully, use the last few parts
        if len(parts) >= 2:
            # Take the last 1-2 parts as project name
            if len(parts) == 2:
                # For two parts, if they look like "my-app", keep both
                if len(parts[0]) <= 3 and len(parts[1]) <= 10:
                    return "-".join(parts)
                else:
                    return parts[-1]
            else:
                # For the last two parts, preserve them as-is with dash
                return "-".join(parts[-2:])

        # Single part case
        if len(parts) == 1:
            return parts[0]

        # Final fallback: use the cleaned directory name
        return clean_name if clean_name else dir_name

    def _analyze_single_directory(self, directory: Path, project_name: str) -> Tuple[int, int]:
        """Analyze JSONL files in a single directory"""
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
                logger.exception(self.i18n.t("file_processing_error", path=jsonl_file))
                continue

        # Finalize any remaining streaming messages for this project
        self._finalize_streaming_messages()

        return files_processed, messages_processed

    def _process_jsonl_file(self, file_path: Path, project_stats: ProjectStats) -> int:
        """Process a single JSONL file containing Claude conversation history

        Each line in the JSONL file represents one message in the conversation.
        We extract token usage and cost information from assistant messages.
        """
        messages_processed = 0

        # Use file creation time as fallback when timestamp parsing fails
        try:
            file_stat = file_path.stat()
            file_creation_time = datetime.fromtimestamp(file_stat.st_ctime)
            fallback_date = file_creation_time.strftime("%Y-%m-%d")
        except Exception:
            logger.exception(self.i18n.t("file_creation_time_error", path=file_path))
            fallback_date = "unknown"

        # Clear accumulators at the start of each file to ensure file-level isolation
        self._message_accumulator.clear()
        # Note: Don't clear _counted_message_ids as we want to track unique messages across files

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
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        logger.exception(self.i18n.t("message_processing_error", path=file_path, line=line_number))
                        continue
        except (IOError, OSError, UnicodeDecodeError):
            logger.exception(self.i18n.t("file_read_error", path=file_path))
            return 0

        if messages_processed > 0:
            logger.debug(self.i18n.t("file_processed", filename=file_path.name, count=messages_processed))

        return messages_processed

    def _convert_utc_to_local(self, utc_timestamp_str: str) -> str:
        """Convert UTC timestamp from Claude logs to local timezone date"""
        try:
            # Parse UTC timestamp
            utc_dt = datetime.fromisoformat(utc_timestamp_str.replace("Z", "+00:00"))
            # Convert to local timezone
            local_dt = utc_dt.astimezone()
            return local_dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            logger.exception(self.i18n.t("timezone_conversion_error", timestamp=utc_timestamp_str))
            return "unknown"

    def _process_streaming_message(
        self,
        timestamp: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_creation_tokens: int,
        message_id: str,
    ) -> tuple:
        """Process streaming response with proper deduplication logic

        Implements the "strict session continuation" algorithm:
        - Cross-file duplicates are skipped completely
        - Within-file streaming segments are accumulated correctly
        - Only the final accumulated version is billed

        Returns: (final_input, final_output, final_cache_read, final_cache_creation, should_bill, is_new_message)
        """
        if not message_id:
            return (input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, True, True)

        # Handle session continuation mode: skip all previously billed messages
        if message_id in self._billed_message_ids:
            logger.debug(f"Session continuation: skipping already billed message {message_id}")
            # If we're in session continuation mode and encounter a previously billed message,
            # stay in continuation mode
            self._session_continuation_mode = True
            return (0, 0, 0, 0, False, False)
        else:
            # If we encounter a new message, exit session continuation mode
            if self._session_continuation_mode:
                logger.debug(f"Exiting session continuation mode at message {message_id}")
                self._session_continuation_mode = False

        is_new_message = message_id not in self._counted_message_ids

        # Check if this is a streaming segment (same message_id seen before in this file)
        if message_id in self._message_accumulator:
            # This is a streaming continuation - accumulate output tokens
            prev_data = self._message_accumulator[message_id]

            # ONLY accumulate output_tokens.
            accumulated_output = prev_data["output_tokens"] + output_tokens

            logger.debug(
                f"Streaming continuation for {message_id}: output {prev_data['output_tokens']} + {output_tokens} = {accumulated_output}"
            )

            # Update the accumulator with the new output total, but keep original input/cache values.
            self._message_accumulator[message_id]["output_tokens"] = accumulated_output

            # Do not bill this segment individually. The total will be billed during finalization.
            return (0, 0, 0, 0, False, is_new_message)
        else:
            # First segment of this message
            self._message_accumulator[message_id] = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "timestamp": timestamp,
                "is_new_message": is_new_message,
            }

            # Bill immediately for the first segment
            final_data = self._message_accumulator[message_id]
            self._billed_message_ids.add(message_id)
            self._counted_message_ids.add(message_id)

            return (
                final_data["input_tokens"],
                final_data["output_tokens"],
                final_data["cache_read_tokens"],
                final_data["cache_creation_tokens"],
                True,
                is_new_message,
            )

    def _finalize_streaming_messages(self) -> None:
        """Finalize streaming messages by billing any remaining segments

        This handles cases where streaming messages had multiple segments
        and we need to bill the incremental output tokens.
        """
        if not self._message_accumulator:
            return

        logger.debug(f"Finalizing {len(self._message_accumulator)} accumulated messages")

        # Process any remaining messages that had streaming segments
        for message_id, acc in self._message_accumulator.items():
            if message_id not in self._billed_message_ids:
                # This shouldn't happen with the new logic, but handle it for safety
                logger.debug(f"Billing final version of {message_id}")
                self._billed_message_ids.add(message_id)
                self._counted_message_ids.add(message_id)

        # Clear the accumulator for the next file
        self._message_accumulator.clear()
        # Reset session continuation mode for next file
        self._session_continuation_mode = False

    def _process_message(
        self, data: Dict[str, Any], project_stats: ProjectStats, fallback_date: str = "unknown"
    ) -> bool:
        """Process a single message from Claude conversation log

        Extracts token usage, calculates costs, and updates statistics.
        Only processes 'assistant' type messages as they contain usage data.

        Returns:
            bool: True if message was successfully processed, False otherwise
        """
        # We only track assistant messages as they contain token usage information
        if data.get("type") != "assistant":
            return False

        message = data.get("message", {})
        if not message:
            logger.debug(self.i18n.t("empty_message_data"))
            return False

        usage = message.get("usage", {})
        if not usage:
            logger.debug(self.i18n.t("missing_usage_info"))
            return False

        # Parse token counts from usage field
        try:
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
            cache_creation_tokens = int(usage.get("cache_creation_input_tokens") or 0)
        except (ValueError, TypeError):
            logger.warning(self.i18n.t("token_format_error"), exc_info=True)
            return False

        if input_tokens == 0 and output_tokens == 0:
            return False

        # Get model identifier for cost calculation
        model_name = message.get("model", "unknown")
        if not model_name or model_name == "unknown":
            logger.debug(self.i18n.t("missing_model_info"))

        # Get message ID for streaming response handling
        message_id = message.get("id", "")

        # Convert UTC timestamp to local date, use file date as fallback
        timestamp_str = data.get("timestamp", "")
        if timestamp_str:
            date_str = self._convert_utc_to_local(timestamp_str)
            if date_str == "unknown" and fallback_date != "unknown":
                logger.debug(self.i18n.t("using_file_creation_time", date=fallback_date))
                date_str = fallback_date
        else:
            logger.debug(self.i18n.t("missing_timestamp_info"))
            date_str = fallback_date

        # Process streaming response with proper deduplication
        final_input, final_output, final_cache_read, final_cache_creation, should_bill, is_new_message = (
            self._process_streaming_message(
                timestamp_str,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                message_id,
            )
        )

        # Only update stats if we should bill this message
        if should_bill:
            self._update_stats(
                final_input,
                final_output,
                final_cache_read,
                final_cache_creation,
                model_name,
                project_stats,
                date_str,
                is_new_message,
            )

        return should_bill

    def _update_stats(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_creation_tokens: int,
        model_name: str,
        project_stats: ProjectStats,
        date_str: str,
        is_new_message: bool,
    ):
        """A dedicated method to update all statistical counters."""
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
            logger.exception(self.i18n.t("cost_calculation_error"))
            message_cost = 0.0

        # Update project-level stats
        project_stats.total_input_tokens += input_tokens
        project_stats.total_output_tokens += output_tokens
        project_stats.total_cache_read_tokens += cache_read_tokens
        project_stats.total_cache_creation_tokens += cache_creation_tokens
        project_stats.total_cost += message_cost
        if is_new_message:
            project_stats.total_messages += 1
            project_stats.models_used[model_name] = project_stats.models_used.get(model_name, 0) + 1

        # Update daily stats
        if date_str not in self.daily_stats:
            self.daily_stats[date_str] = DailyStats(date=date_str)
        daily_stats = self.daily_stats[date_str]
        daily_stats.total_input_tokens += input_tokens
        daily_stats.total_output_tokens += output_tokens
        daily_stats.total_cache_read_tokens += cache_read_tokens
        daily_stats.total_cache_creation_tokens += cache_creation_tokens
        daily_stats.total_cost += message_cost
        if is_new_message:
            daily_stats.total_messages += 1
            daily_stats.models_used[model_name] = daily_stats.models_used.get(model_name, 0) + 1

        # Update daily project breakdown
        if project_stats.project_name not in daily_stats.project_breakdown:
            daily_stats.project_breakdown[project_stats.project_name] = ProjectStats(
                project_name=project_stats.project_name
            )
        daily_project_stats = daily_stats.project_breakdown[project_stats.project_name]
        daily_project_stats.total_input_tokens += input_tokens
        daily_project_stats.total_output_tokens += output_tokens
        daily_project_stats.total_cache_read_tokens += cache_read_tokens
        daily_project_stats.total_cache_creation_tokens += cache_creation_tokens
        daily_project_stats.total_cost += message_cost
        if is_new_message:
            daily_project_stats.total_messages += 1
            daily_project_stats.models_used[model_name] = daily_project_stats.models_used.get(model_name, 0) + 1

        # Update global model stats
        if model_name not in self.model_stats:
            self.model_stats[model_name] = ModelStats(model_name=model_name)
        model_stats = self.model_stats[model_name]
        model_stats.total_input_tokens += input_tokens
        model_stats.total_output_tokens += output_tokens
        model_stats.total_cache_read_tokens += cache_read_tokens
        model_stats.total_cache_creation_tokens += cache_creation_tokens
        model_stats.total_cost += message_cost
        if is_new_message:
            model_stats.total_messages += 1

    def _generate_rich_report(self, max_days=10, max_projects=10) -> None:
        """Generate formatted terminal report using Rich library

        Creates up to 5 sections: overall stats, today's usage, daily trends,
        project rankings, and model comparisons. Intelligently hides empty sections.

        Args:
            max_days: Maximum days to show in daily stats (0 = all)
            max_projects: Maximum projects to show in rankings (0 = all)
        """
        # Filter out projects with no token usage
        valid_projects = [p for p in self.project_stats.values() if p.total_tokens > 0]

        if not valid_projects:
            console.print(f"[red]{self.i18n.t('no_data_found')}[/red]")
            return

        # Aggregate statistics across all valid projects
        total_input_tokens = sum(p.total_input_tokens for p in valid_projects)
        total_output_tokens = sum(p.total_output_tokens for p in valid_projects)
        total_cache_read_tokens = sum(p.total_cache_read_tokens for p in valid_projects)
        total_cache_creation_tokens = sum(p.total_cache_creation_tokens for p in valid_projects)
        total_cost = sum(p.total_cost for p in valid_projects)
        total_messages = sum(p.total_messages for p in valid_projects)

        # 1. Overall statistics summary
        summary_table = Table(
            title=self.i18n.t("overall_stats"), box=box.ROUNDED, show_header=True, header_style="bold cyan"
        )
        summary_table.add_column(self.i18n.t("metric"), style="cyan", no_wrap=True, width=20)
        summary_table.add_column(self.i18n.t("value"), style="yellow", justify="right", width=20)

        summary_table.add_row(self.i18n.t("valid_projects"), f"{len(valid_projects)}")
        summary_table.add_row(self.i18n.t("input_tokens"), f"{total_input_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t("output_tokens"), f"{total_output_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t("cache_read"), f"{total_cache_read_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t("cache_write"), f"{total_cache_creation_tokens/1_000_000:.1f}M")
        summary_table.add_row(self.i18n.t("total_cost"), self._format_cost(total_cost))
        summary_table.add_row(self.i18n.t("total_messages"), f"{total_messages:,}")

        console.print("\n")
        console.print(summary_table)

        # Show today's usage only if there's actual activity with costs
        today_str = date.today().isoformat()
        today_stats = self.daily_stats.get(today_str)
        if today_stats and today_stats.project_breakdown and today_stats.total_cost > 0:
            today_table = Table(
                title=f"{self.i18n.t('today_usage')} ({today_str})",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
            )
            today_table.add_column(self.i18n.t("project"), style="cyan", no_wrap=False, max_width=35)
            today_table.add_column(self.i18n.t("input_tokens"), style="bright_blue", justify="right", min_width=8)
            today_table.add_column(self.i18n.t("output_tokens"), style="yellow", justify="right", min_width=8)
            today_table.add_column(self.i18n.t("cache_read"), style="magenta", justify="right", min_width=8)
            today_table.add_column(self.i18n.t("cache_write"), style="bright_magenta", justify="right", min_width=8)
            today_table.add_column(self.i18n.t("messages"), style="red", justify="right", min_width=6)
            today_table.add_column(self.i18n.t("cost"), style="green", justify="right", min_width=8)

            # Rank today's projects by cost to show highest spenders first
            sorted_today_projects = sorted(
                today_stats.project_breakdown.values(), key=lambda x: x.total_cost, reverse=True
            )

            for project in sorted_today_projects:
                if project.total_tokens > 0:  # Only show projects with actual usage
                    today_table.add_row(
                        project.project_name,
                        self._format_number(project.total_input_tokens),
                        self._format_number(project.total_output_tokens),
                        self._format_number(project.total_cache_read_tokens),
                        self._format_number(project.total_cache_creation_tokens),
                        self._format_number(project.total_messages),
                        self._format_cost(project.total_cost),
                    )

            # Add total row
            today_table.add_section()
            today_table.add_row(
                self.i18n.t("total"),
                self._format_number(today_stats.total_input_tokens),
                self._format_number(today_stats.total_output_tokens),
                self._format_number(today_stats.total_cache_read_tokens),
                self._format_number(today_stats.total_cache_creation_tokens),
                self._format_number(today_stats.total_messages),
                self._format_cost(today_stats.total_cost),
            )

            console.print("\n")
            console.print(today_table)

        # Show historical daily trends (exclude today, require historical data)
        valid_daily_stats = {k: v for k, v in self.daily_stats.items() if v.total_tokens > 0}
        today_str = date.today().isoformat()

        # Only show daily trends if we have historical data beyond today
        historical_stats = {k: v for k, v in valid_daily_stats.items() if k != today_str}

        if historical_stats:
            title_suffix = (
                f"({self.i18n.t('recent_days', days=max_days)})" if max_days > 0 else f"({self.i18n.t('all_data')})"
            )
            daily_table = Table(
                title=f"{self.i18n.t('daily_stats')} {title_suffix}",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
            )
            daily_table.add_column(self.i18n.t("date"), style="cyan", justify="center", min_width=10)
            daily_table.add_column(self.i18n.t("input_tokens"), style="bright_blue", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t("output_tokens"), style="yellow", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t("cache_read"), style="magenta", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t("cache_write"), style="bright_magenta", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t("messages"), style="red", justify="right", min_width=6)
            daily_table.add_column(self.i18n.t("cost"), style="green", justify="right", min_width=8)
            daily_table.add_column(self.i18n.t("active_projects"), style="orange3", justify="right", min_width=8)

            # Generate date range for display
            today = date.today()

            if max_days > 0:
                # Show last N days of data (excluding today)
                date_list = [(today - timedelta(days=i + 1)).isoformat() for i in range(max_days)]
                # Filter to only dates with actual data
                date_list = [d for d in date_list if d in valid_daily_stats]
            else:
                # Show all historical data
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

        # Show project rankings (always shown if we have valid projects)
        valid_projects = [p for p in self.project_stats.values() if p.total_tokens > 0]
        if valid_projects:
            title_suffix = (
                f"({self.i18n.t('top_n', n=max_projects)})" if max_projects > 0 else f"({self.i18n.t('all_data')})"
            )
            projects_table = Table(
                title=f"{self.i18n.t('project_stats')} {title_suffix}",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
            )
            projects_table.add_column(self.i18n.t("project"), style="cyan", no_wrap=False, max_width=35)
            projects_table.add_column(self.i18n.t("input_tokens"), style="bright_blue", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t("output_tokens"), style="yellow", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t("cache_read"), style="magenta", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t("cache_write"), style="bright_magenta", justify="right", min_width=8)
            projects_table.add_column(self.i18n.t("messages"), style="red", justify="right", min_width=6)
            projects_table.add_column(self.i18n.t("cost"), style="green", justify="right", min_width=8)

            # Rank projects by total cost
            sorted_projects = sorted(valid_projects, key=lambda x: x.total_cost, reverse=True)
            # Apply display limit if specified
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

        # Show model comparison only when using multiple models
        valid_models = [m for m in self.model_stats.values() if m.total_tokens > 0]
        if len(valid_models) >= 2:
            models_table = Table(
                title=self.i18n.t("model_stats"), box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            models_table.add_column(self.i18n.t("model"), style="cyan", no_wrap=False, max_width=35)
            models_table.add_column(self.i18n.t("input_tokens"), style="bright_blue", justify="right", min_width=8)
            models_table.add_column(self.i18n.t("output_tokens"), style="yellow", justify="right", min_width=8)
            models_table.add_column(self.i18n.t("cache_read"), style="magenta", justify="right", min_width=8)
            models_table.add_column(self.i18n.t("cache_write"), style="bright_magenta", justify="right", min_width=8)
            models_table.add_column(self.i18n.t("messages"), style="red", justify="right", min_width=6)
            models_table.add_column(self.i18n.t("cost"), style="green", justify="right", min_width=8)

            # Rank models by total cost
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
        """Format large numbers with K/M suffixes for readability"""
        if num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        else:
            return str(num)

    def export_json(self, output_path: Path) -> None:
        """Export analysis results to JSON file for external processing"""
        # Structure data for JSON serialization
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

        # Export project statistics
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

        # Export daily statistics with project breakdowns
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

        # Export model statistics
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

        # Write formatted JSON to file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        logger.info(self.i18n.t("json_exported", path=output_path))
