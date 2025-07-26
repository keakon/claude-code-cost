#!/usr/bin/env python3
"""Generate test data for Claude Code Cost Calculator testing

Creates mock Claude project files with realistic usage patterns
for testing the analyzer across different platforms and Python versions.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path


def generate_message_data(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0, days_ago: int = 0) -> dict:
    """Generate a single message data entry"""
    # Generate timestamp for specified days ago
    message_time = datetime.now() - timedelta(days=days_ago)
    
    return {
        "id": str(uuid.uuid4()),
        "timestamp": message_time.isoformat() + "Z",
        "type": "assistant",
        "message": {
            "id": str(uuid.uuid4()),
            "content": [{"type": "text", "text": f"Sample response from {model} model for testing"}],
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_write_tokens,
                "cache_read_input_tokens": cache_read_tokens
            }
        }
    }


def create_project_data(project_name: str, messages: list) -> list:
    """Create a list of JSONL entries for a project"""
    project_data = []
    
    # Add project metadata
    project_data.append({
        "type": "project_metadata",
        "project_name": project_name,
        "created_at": (datetime.now() - timedelta(days=7)).isoformat() + "Z"
    })
    
    # Add messages
    for msg in messages:
        project_data.append(msg)
    
    return project_data


def write_project_file(project_dir: Path, project_name: str, data: list):
    """Write project data to JSONL file"""
    # Claude uses directory names starting with '-'
    claude_dir_name = f"-{project_name}"
    project_path = project_dir / claude_dir_name
    project_path.mkdir(exist_ok=True)
    
    # Create a messages file
    messages_file = project_path / "messages.jsonl"
    with open(messages_file, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry) + "\n")


def generate_test_data(base_dir: str):
    """Generate comprehensive test data for different scenarios"""
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    
    # Test Project 1: Mixed models with different usage patterns (spread across days)
    project1_messages = [
        generate_message_data("claude-3-5-sonnet-20241022", 1000, 500, 100, 50, days_ago=1),
        generate_message_data("claude-3-5-sonnet-20241022", 1500, 800, 200, 0, days_ago=2),
        generate_message_data("claude-3-opus-20240229", 2000, 1200, 0, 100, days_ago=4),
        generate_message_data("claude-3-haiku-20240307", 500, 300, 50, 25, days_ago=7),
    ]
    
    project1_data = create_project_data("test-project-mixed-models", project1_messages)
    write_project_file(base_path, "test-project-mixed-models", project1_data)
    
    # Test Project 2: High volume usage (for tier testing, recent activity)
    project2_messages = [
        generate_message_data("gemini-2.0-flash-exp", 150000, 80000, days_ago=0),  # Today
        generate_message_data("gemini-2.0-flash-exp", 300000, 150000, days_ago=1),  # Yesterday
        generate_message_data("qwen3-coder", 30000, 15000, days_ago=2),  # Tier 1
        generate_message_data("qwen3-coder", 100000, 50000, days_ago=3),  # Tier 2
        generate_message_data("qwen3-coder", 200000, 100000, days_ago=5),  # Tier 3
        generate_message_data("qwen3-coder", 300000, 200000, days_ago=6),  # Tier 4
    ]
    
    project2_data = create_project_data("test-project-high-volume", project2_messages)
    write_project_file(base_path, "test-project-high-volume", project2_data)
    
    # Test Project 3: Cache heavy usage (spread over time)
    project3_messages = [
        generate_message_data("claude-3-5-sonnet-20241022", 5000, 2000, 10000, 1000, days_ago=3),
        generate_message_data("claude-3-5-sonnet-20241022", 3000, 1500, 15000, 500, days_ago=8),
        generate_message_data("claude-3-opus-20240229", 8000, 4000, 20000, 2000, days_ago=9),
    ]
    
    project3_data = create_project_data("test-project-cache-heavy", project3_messages)
    write_project_file(base_path, "test-project-cache-heavy", project3_data)
    
    # Test Project 4: Single model consistency (recent regular usage)
    project4_messages = [
        generate_message_data("claude-3-haiku-20240307", 800, 400, days_ago=1),
        generate_message_data("claude-3-haiku-20240307", 1200, 600, days_ago=4),
        generate_message_data("claude-3-haiku-20240307", 900, 450, days_ago=8),
    ]
    
    project4_data = create_project_data("test-project-single-model", project4_messages)
    write_project_file(base_path, "test-project-single-model", project4_data)
    
    # Test Project 5: Edge cases and unknown models (older activity)
    project5_messages = [
        generate_message_data("unknown-model-test", 1000, 500, days_ago=10),  # Should have zero cost
        generate_message_data("claude-3-5-sonnet-20241022", 0, 0, days_ago=9),  # Zero usage
        generate_message_data("gemini-1.5-pro", 10, 5, days_ago=6),  # Very small usage
    ]
    
    project5_data = create_project_data("test-project-edge-cases", project5_messages)
    write_project_file(base_path, "test-project-edge-cases", project5_data)
    
    print(f"[OK] Generated test data in: {base_path}")
    print(f"[INFO] Created {len(list(base_path.iterdir()))} test projects")
    
    # Verify the structure
    total_files = 0
    for project_dir in base_path.iterdir():
        if project_dir.is_dir():
            files = list(project_dir.glob("*.jsonl"))
            total_files += len(files)
            print(f"   [FILE] {project_dir.name}: {len(files)} JSONL files")
    
    print(f"[STATS] Total test files: {total_files}")


def main():
    """Main entry point for test data generation"""
    if len(sys.argv) != 2:
        print("Usage: python generate_test_data.py <output_directory>")
        print("Example: python generate_test_data.py test_data/.claude/projects")
        sys.exit(1)
    
    output_dir = sys.argv[1]
    
    try:
        generate_test_data(output_dir)
        print("\n[SUCCESS] Test data generation completed successfully!")
    except Exception as e:
        print(f"[ERROR] Error generating test data: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()