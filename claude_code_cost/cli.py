#!/usr/bin/env python3
"""Command-line interface for Claude Code Cost Calculator

Provides argument parsing, configuration loading, and coordinates
the analysis workflow from command line invocation.
"""

import argparse
import logging
from pathlib import Path

from claude_code_cost.analyzer import ClaudeHistoryAnalyzer
from claude_code_cost.billing import load_currency_config
from claude_code_cost.i18n import get_i18n, t


def main():
    """Main entry point for the CLI application"""
    # Parse language parameter early for i18n setup
    import sys
    language = None
    if '--language' in sys.argv:
        try:
            lang_index = sys.argv.index('--language')
            if lang_index + 1 < len(sys.argv):
                language = sys.argv[lang_index + 1]
        except (ValueError, IndexError):
            pass
    
    # Set up i18n based on detected/specified language
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

    # Apply language setting if explicitly provided
    if args.language:
        get_i18n(args.language)

    # Configure logging system
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Load base currency configuration from files
    currency_config = load_currency_config()

    # Override config with command-line arguments if provided
    if args.currency is not None:
        currency_config["display_unit"] = args.currency
    if args.usd_to_cny is not None:
        currency_config["usd_to_cny"] = args.usd_to_cny

    # Initialize analyzer and process all project files
    analyzer = ClaudeHistoryAnalyzer(args.data_dir, currency_config, args.language)
    analyzer.analyze_directory(args.data_dir)

    # Display formatted results to terminal
    analyzer._generate_rich_report(max_days=args.max_days, max_projects=args.max_projects)

    # Export to JSON if requested
    if args.export_json:
        analyzer.export_json(args.export_json)


if __name__ == "__main__":
    main()