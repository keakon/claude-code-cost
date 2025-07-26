#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path

from claude_code_cost.analyzer import ClaudeHistoryAnalyzer
from claude_code_cost.config import load_currency_config
from claude_code_cost.i18n import get_i18n, t


def main():
    """主函数"""
    # 首先解析语言参数，如果存在的话
    import sys
    language = None
    if '--language' in sys.argv:
        try:
            lang_index = sys.argv.index('--language')
            if lang_index + 1 < len(sys.argv):
                language = sys.argv[lang_index + 1]
        except (ValueError, IndexError):
            pass
    
    # 根据语言参数初始化国际化
    i18n = get_i18n(language)
    
    parser = argparse.ArgumentParser(description=i18n.t('app_description'))
    parser.add_argument(
        "--data-dir", type=Path, default=Path.home() / ".claude" / "projects", 
        help=i18n.t('data_dir_help')
    )
    parser.add_argument("--export-json", type=Path, help=i18n.t('export_json_help'))
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="WARNING", 
        help=i18n.t('log_level_help')
    )
    parser.add_argument("--max-days", type=int, default=10, help=i18n.t('max_days_help'))
    parser.add_argument("--max-projects", type=int, default=10, help=i18n.t('max_projects_help'))
    parser.add_argument(
        "--currency", choices=["USD", "CNY"], default=None, help=i18n.t('currency_help')
    )
    parser.add_argument("--usd-to-cny", type=float, default=None, help=i18n.t('usd_to_cny_help'))
    parser.add_argument(
        "--language", choices=["en", "zh"], default=None, help=i18n.t('language_help')
    )

    args = parser.parse_args()

    # 确保语言设置正确应用
    if args.language:
        get_i18n(args.language)

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
    analyzer = ClaudeHistoryAnalyzer(args.data_dir, currency_config, args.language)
    analyzer.analyze_directory(args.data_dir)

    # 生成报告
    analyzer._generate_rich_report(max_days=args.max_days, max_projects=args.max_projects)

    # 导出JSON（如果指定了输出路径）
    if args.export_json:
        analyzer.export_json(args.export_json)


if __name__ == "__main__":
    main()