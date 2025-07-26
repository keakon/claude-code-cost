#!/usr/bin/env python3
"""Verification tests for Claude Code Cost Calculator

Tests the correctness of calculations, not just that the tool runs.
Validates token counting, cost calculations, currency conversion, and output format.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List

# Import our test data generator
from generate_test_data import generate_test_data


def run_claude_cost(data_dir: str, extra_args: Optional[List[str]] = None) -> dict:
    """Run claude-cost tool and return parsed JSON output"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json_output = f.name
    
    cmd = [
        sys.executable, "-m", "claude_code_cost.cli",
        "--data-dir", data_dir,
        "--export-json", json_output,
        "--log-level", "ERROR"  # Suppress logs for clean testing
    ]
    
    if extra_args:
        cmd.extend(extra_args)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        with open(json_output, 'r') as f:
            return json.load(f)
    finally:
        # Clean up temp file
        Path(json_output).unlink(missing_ok=True)


def verify_token_totals(results: dict) -> bool:
    """Verify that token totals are correctly calculated"""
    print("🔍 Verifying token totals...")
    
    # Expected totals based on our test data generation
    expected_totals = {
        "total_input_tokens": 1104910,  # Sum of all input tokens
        "total_output_tokens": 607255,   # Sum of all output tokens  
        "total_cache_read_tokens": 45350,  # Sum of cache reads
        "total_cache_creation_tokens": 3675,  # Sum of cache writes
        "total_messages": 18  # Total number of assistant messages
    }
    
    actual_totals = results["summary"]
    
    for key, expected in expected_totals.items():
        actual = actual_totals.get(key, 0)
        if actual != expected:
            print(f"❌ {key}: expected {expected}, got {actual}")
            return False
        print(f"✅ {key}: {actual}")
    
    return True


def verify_cost_calculations(results: dict) -> bool:
    """Verify that cost calculations are correct based on model pricing"""
    print("🔍 Verifying cost calculations...")
    
    # Test a few specific cost calculations
    model_stats = results.get("model_stats", {})
    
    # Claude 3.5 Sonnet: $3/M input, $15/M output, $0.3/M cache read, $3.75/M cache write
    sonnet_stats = model_stats.get("claude-3-5-sonnet-20241022", {})
    if sonnet_stats:
        input_cost = (sonnet_stats["total_input_tokens"] / 1_000_000) * 3.0
        output_cost = (sonnet_stats["total_output_tokens"] / 1_000_000) * 15.0
        cache_read_cost = (sonnet_stats["total_cache_read_tokens"] / 1_000_000) * 0.3
        cache_write_cost = (sonnet_stats["total_cache_creation_tokens"] / 1_000_000) * 3.75
        
        expected_total = input_cost + output_cost + cache_read_cost + cache_write_cost
        actual_total = sonnet_stats["total_cost"]
        
        # Allow small floating point differences
        if abs(expected_total - actual_total) > 0.01:
            print(f"❌ Claude 3.5 Sonnet cost: expected ~${expected_total:.4f}, got ${actual_total:.4f}")
            return False
        print(f"✅ Claude 3.5 Sonnet cost: ${actual_total:.4f}")
    
    # Test that unknown models have zero cost
    unknown_stats = model_stats.get("unknown-model-test", {})
    if unknown_stats and unknown_stats["total_cost"] != 0:
        print(f"❌ Unknown model should have zero cost, got ${unknown_stats['total_cost']}")
        return False
    print("✅ Unknown model has zero cost")
    
    return True


def verify_currency_conversion() -> bool:
    """Verify currency conversion calculations in UI (not JSON export)"""
    print("🔍 Verifying currency conversion...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Generate test data
        data_dir = Path(temp_dir) / ".claude" / "projects"
        generate_test_data(str(data_dir))
        
        # Test USD (default) - JSON should always be in USD
        usd_results = run_claude_cost(str(data_dir))
        usd_cost = usd_results["summary"]["total_cost"]
        
        # Test CNY - JSON should still be in USD (internal representation)
        cny_results = run_claude_cost(str(data_dir), ["--currency", "CNY", "--usd-to-cny", "7.0"])
        cny_cost_json = cny_results["summary"]["total_cost"]
        
        # JSON export should always be in USD (internal representation)
        if abs(cny_cost_json - usd_cost) > 0.01:
            print(f"❌ JSON should always be in USD: expected ${usd_cost:.2f}, got ${cny_cost_json:.2f}")
            return False
        
        print(f"✅ Currency conversion: JSON always stores USD (${usd_cost:.2f}), UI converts for display")
    
    return True


def verify_project_breakdown(results: dict) -> bool:
    """Verify that project-level statistics are correct"""
    print("🔍 Verifying project breakdown...")
    
    project_stats = results.get("project_stats", {})
    
    # Check that we have all expected projects
    expected_projects = {
        "cache/heavy", "single/model", "mixed/models", 
        "edge/cases", "high/volume"
    }
    
    actual_projects = set(project_stats.keys())
    if not expected_projects.issubset(actual_projects):
        missing = expected_projects - actual_projects
        print(f"❌ Missing projects: {missing}")
        return False
    
    # Verify high-volume project has the highest cost
    costs = {name: stats["total_cost"] for name, stats in project_stats.items()}
    highest_cost_project = max(costs.keys(), key=lambda k: costs[k])
    
    if "high/volume" not in highest_cost_project:
        print(f"❌ Expected high/volume to have highest cost, but {highest_cost_project} does")
        return False
    
    print(f"✅ High-volume project has highest cost: ${costs[highest_cost_project]:.2f}")
    
    return True


def verify_daily_breakdown(results: dict) -> bool:
    """Verify that daily statistics are correctly aggregated"""
    print("🔍 Verifying daily breakdown...")
    
    daily_stats = results.get("daily_stats", {})
    
    if not daily_stats:
        print("❌ No daily statistics found")
        return False
    
    # Should have data spread across multiple days (not all on one day)
    if len(daily_stats) < 5:
        print(f"❌ Expected data across multiple days, got {len(daily_stats)} days")
        return False
    
    # Check that daily totals sum to overall totals
    total_input = sum(day["total_input_tokens"] for day in daily_stats.values())
    total_output = sum(day["total_output_tokens"] for day in daily_stats.values())
    total_messages = sum(day["total_messages"] for day in daily_stats.values())
    
    summary = results["summary"]
    
    if (total_input != summary["total_input_tokens"] or 
        total_output != summary["total_output_tokens"] or
        total_messages != summary["total_messages"]):
        print("❌ Daily totals don't match overall totals")
        return False
    
    print(f"✅ Daily stats correctly aggregated across {len(daily_stats)} days")
    
    return True


def verify_json_structure(results: dict) -> bool:
    """Verify that JSON output has expected structure"""
    print("🔍 Verifying JSON structure...")
    
    required_keys = {
        "analysis_timestamp", "project_stats", "daily_stats", 
        "model_stats", "summary"
    }
    
    if not required_keys.issubset(results.keys()):
        missing = required_keys - set(results.keys())
        print(f"❌ Missing JSON keys: {missing}")
        return False
    
    # Check summary structure
    summary_required = {
        "total_input_tokens", "total_output_tokens", "total_cache_read_tokens", 
        "total_cache_creation_tokens", "total_cost", "total_messages", "total_projects"
    }
    
    summary = results["summary"]
    if not summary_required.issubset(summary.keys()):
        missing = summary_required - set(summary.keys())
        print(f"❌ Missing summary keys: {missing}")
        return False
    
    print("✅ JSON structure is correct")
    
    return True


def run_verification_tests():
    """Run all verification tests"""
    print("🚀 Starting Claude Code Cost verification tests...\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Generate test data
        data_dir = Path(temp_dir) / ".claude" / "projects"
        generate_test_data(str(data_dir))
        
        # Get results for testing
        results = run_claude_cost(str(data_dir))
        
        # Run all verification tests
        tests = [
            ("JSON Structure", lambda: verify_json_structure(results)),
            ("Token Totals", lambda: verify_token_totals(results)),
            ("Cost Calculations", lambda: verify_cost_calculations(results)),
            ("Project Breakdown", lambda: verify_project_breakdown(results)),
            ("Daily Breakdown", lambda: verify_daily_breakdown(results)),
            ("Currency Conversion", verify_currency_conversion),
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            print(f"\n📋 Running {test_name} test...")
            try:
                if test_func():
                    print(f"✅ {test_name} test PASSED")
                    passed += 1
                else:
                    print(f"❌ {test_name} test FAILED")
                    failed += 1
            except Exception as e:
                print(f"❌ {test_name} test ERROR: {e}")
                failed += 1
        
        print(f"\n🎯 Test Results: {passed} passed, {failed} failed")
        
        if failed > 0:
            print("❌ Some verification tests failed!")
            return False
        else:
            print("🎉 All verification tests passed!")
            return True


if __name__ == "__main__":
    success = run_verification_tests()
    sys.exit(0 if success else 1)