"""
计费相关功能模块

从main.py提取的计费相关函数，包括模型成本计算和配置加载功能。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

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

# 配置日志
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
                package_files = files("claude-cost") if __package__ else files(__name__.split('.')[0])
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
        user_config_path = Path.home() / ".claude-cost" / config_file
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
        currency_config: 货币配置

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