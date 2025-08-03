"""Billing and cost calculation functionality

Handles model pricing, configuration loading, and cost calculations
for different AI models with support for multi-tier pricing and currencies.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

try:
    # Python 3.9+
    from importlib.resources import files
except ImportError:
    # Fallback - use __file__ method
    files = None

import yaml

# Configure logging
logger = logging.getLogger(__name__)

DEFAULT_USD_TO_CNY = 7.0


def get_default_config() -> Dict:
    """Get built-in default configuration with pricing for all supported models"""
    return {
        "currency": {"usd_to_cny": 7.0, "display_unit": "USD"},
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
            "gemini-2.5-pro": {
                "tiers": [
                    {"threshold": 200000, "input_per_million": 1.25, "output_per_million": 10.0},
                    {"input_per_million": 2.50, "output_per_million": 15.0},
                ]
            },
            "gemini-1.5-pro": {"input_per_million": 1.25, "output_per_million": 5.0},
            "qwen3-coder": {
                "currency": "CNY",
                "tiers": [
                    {"threshold": 32000, "input_per_million": 4.0, "output_per_million": 16.0},
                    {"threshold": 128000, "input_per_million": 6.0, "output_per_million": 24.0},
                    {"threshold": 256000, "input_per_million": 10.0, "output_per_million": 40.0},
                    {"input_per_million": 20.0, "output_per_million": 200.0},
                ],
            },
        },
    }


def deep_merge(base_dict: Dict, update_dict: Dict) -> Dict:
    """Recursively merge two dictionaries, with update_dict taking precedence"""
    result = base_dict.copy()
    for key, value in update_dict.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_full_config(config_file: str = "model_pricing.yaml") -> Dict:
    """Load complete configuration with fallback hierarchy

    Priority order:
    1. Built-in defaults (always available)
    2. Package configuration file
    3. User configuration (~/.claude-code-cost/model_pricing.yaml)

    Higher priority configs override lower ones via deep merge.
    """
    # Start from default configuration
    config = get_default_config()

    try:
        # First try to load from package resources (for installed package)
        if files is not None:
            try:
                # Python 3.9+ or has importlib_resources
                package_files = files("claude_code_cost") if __package__ else files(__name__.split(".")[0])
                config_data = (package_files / config_file).read_text(encoding="utf-8")
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    user_config = yaml.safe_load(config_data)
                else:
                    user_config = json.loads(config_data)

                # Deep merge user configuration
                if user_config:
                    config = deep_merge(config, user_config)
                return config
            except Exception:
                logger.debug("Unable to load config file via importlib.resources, trying file path method")

        # Fallback to local file (for development/source installs)
        config_path = Path(__file__).parent / config_file
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    user_config = yaml.safe_load(f)
                else:
                    user_config = json.load(f)

                # Deep merge user configuration
                if user_config:
                    config = deep_merge(config, user_config)

        # Finally, check for user-specific overrides
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
                        logger.info(f"User configuration file loaded: {user_config_path}")
            except Exception:
                logger.warning(f"Unable to load user configuration file {user_config_path}", exc_info=True)

    except Exception:
        logger.warning("Error occurred during configuration file loading, using default configuration", exc_info=True)

    return config


def load_model_pricing(config_file: str = "model_pricing.yaml") -> Dict:
    """Extract pricing configuration from full config"""
    full_config = load_full_config(config_file)
    return full_config.get("pricing", {})


def load_currency_config(config_file: str = "model_pricing.yaml") -> Dict:
    """Extract currency configuration from full config"""
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
    """Calculate cost for a specific model and token usage

    Supports both standard pricing and multi-tier pricing models.
    Handles currency conversion when models specify non-USD pricing.

    Args:
        model_name: Name of the AI model (e.g., 'sonnet', 'opus')
        input_tokens: Number of input tokens consumed
        output_tokens: Number of output tokens generated
        cache_read_tokens: Number of tokens read from cache
        cache_creation_tokens: Number of tokens written to cache
        pricing_config: Model pricing configuration dict
        model_config_cache: Cache to avoid repeated config lookups
        currency_config: Currency conversion settings

    Returns:
        Total cost in USD (after currency conversion if needed)
    """
    if not pricing_config:
        return 0.0

    # Use cached config if available to avoid repeated lookups
    if model_config_cache and model_name in model_config_cache:
        model_config = model_config_cache[model_name]
    else:
        # Find pricing config using flexible matching strategy
        model_config = None

        # 1. Try exact name match first (most reliable)
        for config_key, config_value in pricing_config.items():
            if model_name.lower() == config_key.lower():
                model_config = config_value
                break

        # 2. Try substring match (for model variants like 'claude-3-sonnet')
        # Sort by length in descending order to prioritize longer, more specific names
        if not model_config:
            sorted_keys = sorted(pricing_config.keys(), key=len, reverse=True)
            for config_key in sorted_keys:
                if config_key.lower() in model_name.lower():
                    model_config = pricing_config[config_key]
                    break

        # 3. No matching config found - this model is free or unsupported
        if not model_config:
            logger.debug(f"Pricing configuration not found for model {model_name}, cost set to 0")
            return 0.0

        # Store in cache for future use
        if model_config_cache is not None:
            model_config_cache[model_name] = model_config

    # Apply pricing model (supports both standard and multi-tier)
    input_rate = 0
    output_rate = 0
    cache_read_rate = 0
    cache_write_rate = 0

    if "tiers" in model_config:
        # Multi-tier pricing: select appropriate tier based on input tokens
        tiers = model_config.get("tiers", [])
        selected_tier = None

        # Sort tiers by threshold (infinite thresholds go last)
        def sort_key(tier):
            threshold = tier.get("threshold")
            if threshold is None:
                return float("inf")  # Unlimited tier goes last
            return float(threshold)

        sorted_tiers = sorted(tiers, key=sort_key)

        # Find the first tier that can handle our token count
        for tier in sorted_tiers:
            threshold = tier.get("threshold")
            if threshold is None:  # Unlimited tier
                selected_tier = tier
                break
            elif input_tokens <= float(threshold):
                selected_tier = tier
                break

        # Use last tier if no specific tier matches (shouldn't happen with good config)
        if selected_tier is None and sorted_tiers:
            selected_tier = sorted_tiers[-1]

        if selected_tier:
            input_rate = selected_tier.get("input_per_million", 0)
            output_rate = selected_tier.get("output_per_million", 0)
            cache_read_rate = selected_tier.get("cache_read_per_million", 0)
            cache_write_rate = selected_tier.get("cache_write_per_million", 0)
    else:
        # Standard single-rate pricing
        input_rate = model_config.get("input_per_million", 0)
        output_rate = model_config.get("output_per_million", 0)
        cache_read_rate = model_config.get("cache_read_per_million", 0)
        cache_write_rate = model_config.get("cache_write_per_million", 0)

    # Calculate individual cost components
    input_cost = (input_tokens / 1_000_000) * input_rate
    output_cost = (output_tokens / 1_000_000) * output_rate
    cache_read_cost = (cache_read_tokens / 1_000_000) * cache_read_rate
    cache_creation_cost = (cache_creation_tokens / 1_000_000) * cache_write_rate

    total_cost = input_cost + output_cost + cache_read_cost + cache_creation_cost

    # Convert to USD if model uses different currency (e.g., CNY for Chinese models)
    model_currency = model_config.get("currency", "USD")
    if model_currency == "CNY" and currency_config:
        # Convert from model's native currency to USD for internal consistency
        exchange_rate = currency_config.get("usd_to_cny", DEFAULT_USD_TO_CNY)
        total_cost = total_cost / exchange_rate

    return total_cost
