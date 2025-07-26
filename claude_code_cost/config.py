import json
import logging
from pathlib import Path
from typing import Any, Dict

try:
    # Python 3.9+
    from importlib.resources import files
except ImportError:
    # Python 3.8 fallback
    try:
        from importlib_resources import files
    except ImportError:
        # Ultimate fallback - use __file__ method
        files = None

import yaml

logger = logging.getLogger(__name__)
DEFAULT_USD_TO_CNY = 7.0


def get_default_config() -> Dict:
    """获取默认配置"""
    return {
        "currency": {
            "usd_to_cny": 7.0,
            "display_unit": "USD"
        },
        "pricing": {
            "sonnet": {
                "input_per_million": 3.0,
                "output_per_million": 15.0,
                "cache_read_per_million": 0.3,
                "cache_write_per_million": 3.75
            },
            "opus": {
                "input_per_million": 15.0,
                "output_per_million": 75.0,
                "cache_read_per_million": 1.5,
                "cache_write_per_million": 18.75
            },
            "gemini-2.5-pro": {
                "tiers": [
                    {
                        "threshold": 200000,
                        "input_per_million": 1.25,
                        "output_per_million": 10.0
                    },
                    {
                        "input_per_million": 2.50,
                        "output_per_million": 15.0
                    }
                ]
            },
            "gemini-1.5-pro": {
                "input_per_million": 1.25,
                "output_per_million": 5.0
            },
            "qwen3-coder": {
                "currency": "CNY",
                "tiers": [
                    {
                        "threshold": 32000,
                        "input_per_million": 4.0,
                        "output_per_million": 16.0
                    },
                    {
                        "threshold": 128000,
                        "input_per_million": 6.0,
                        "output_per_million": 24.0
                    },
                    {
                        "threshold": 256000,
                        "input_per_million": 10.0,
                        "output_per_million": 40.0
                    },
                    {
                        "input_per_million": 20.0,
                        "output_per_million": 200.0
                    }
                ]
            }
        }
    }


def deep_merge(base_dict: Dict, update_dict: Dict) -> Dict:
    """深度合并两个字典"""
    result = base_dict.copy()
    for key, value in update_dict.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_full_config(config_file: str = "model_pricing.yaml") -> Dict:
    """加载完整配置（包括定价和货币配置）"""
    # 从默认配置开始
    config = get_default_config()
    
    try:
        # 优先使用 importlib.resources 加载打包后的资源文件
        if files is not None:
            try:
                # Python 3.9+ 或有 importlib_resources
                package_files = files("claude_code_cost")
                config_data = (package_files / config_file).read_text(encoding="utf-8")
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    user_config = yaml.safe_load(config_data)
                else:
                    user_config = json.loads(config_data)
                
                # 深度合并用户配置
                if user_config:
                    config = deep_merge(config, user_config)
                return config
            except Exception:
                logger.debug("无法通过 importlib.resources 加载配置文件，尝试文件路径方式")
        
        # 回退到文件路径方式（开发环境或作为脚本运行）
        config_path = Path(__file__).parent / config_file
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    user_config = yaml.safe_load(f)
                else:
                    user_config = json.load(f)
                
                # 深度合并用户配置
                if user_config:
                    config = deep_merge(config, user_config)
        
        # 尝试从用户目录加载配置文件
        user_config_path = Path.home() / ".claude-code-cost" / config_file
        if user_config_path.exists():
            try:
                with open(user_config_path, "r", encoding="utf-8") as f:
                    if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                        user_config = yaml.safe_load(f)
                    else:
                        user_config = json.load(f)
                    
                    # 深度合并用户配置
                    if user_config:
                        config = deep_merge(config, user_config)
                        logger.info(f"已加载用户配置文件: {user_config_path}")
            except Exception:
                logger.warning(f"无法加载用户配置文件 {user_config_path}", exc_info=True)
    
    except Exception:
        logger.warning(f"配置文件加载过程中出现错误，使用默认配置", exc_info=True)
    
    return config


def load_model_pricing(config_file: str = "model_pricing.yaml") -> Dict:
    """加载模型定价配置（支持YAML和JSON格式）"""
    full_config = load_full_config(config_file)
    return full_config.get("pricing", {})


def load_currency_config(config_file: str = "model_pricing.yaml") -> Dict:
    """加载货币配置"""
    full_config = load_full_config(config_file)
    return full_config.get("currency", {"usd_to_cny": DEFAULT_USD_TO_CNY, "display_unit": "USD"})