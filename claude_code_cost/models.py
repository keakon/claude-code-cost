"""Data models for Claude usage statistics

Defines dataclasses that represent different levels of usage statistics:
project-level, daily aggregates, and per-model breakdowns.
"""


from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProjectStats:
    """Statistics for a single Claude project
    
    Tracks token usage, costs, and metadata for one project across its lifetime.
    """

    project_name: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_messages: int = 0
    total_cost: float = 0.0
    models_used: Dict[str, int] = field(default_factory=dict)
    first_message_date: Optional[str] = None
    last_message_date: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed (input + output)"""
        return self.total_input_tokens + self.total_output_tokens


@dataclass
class ModelStats:
    """Statistics for a specific AI model across all projects
    
    Aggregates usage and costs for one model (e.g., 'sonnet', 'opus') globally.
    """

    model_name: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_messages: int = 0
    total_cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed (input + output)"""
        return self.total_input_tokens + self.total_output_tokens


@dataclass
class DailyStats:
    """Statistics aggregated by calendar date
    
    Contains total usage for one day plus breakdowns by project and model.
    """

    date: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_messages: int = 0
    total_cost: float = 0.0
    models_used: Dict[str, int] = field(default_factory=dict)
    projects_active: int = 0
    project_breakdown: Dict[str, ProjectStats] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed (input + output)"""
        return self.total_input_tokens + self.total_output_tokens