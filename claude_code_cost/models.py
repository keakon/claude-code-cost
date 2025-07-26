from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProjectStats:
    """项目统计数据"""

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
        return self.total_input_tokens + self.total_output_tokens


@dataclass
class ModelStats:
    """模型统计数据"""

    model_name: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_messages: int = 0
    total_cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


@dataclass
class DailyStats:
    """每日统计数据"""

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
        return self.total_input_tokens + self.total_output_tokens