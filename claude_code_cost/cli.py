#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path

from claude_code_cost.analyzer import ClaudeHistoryAnalyzer
from claude_code_cost.config import load_currency_config


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Claude Code Cost Calculator - 分析 Claude Code 使用成本")
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
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

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