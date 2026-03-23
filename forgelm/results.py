"""Training result dataclass — importable without heavy ML dependencies."""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TrainResult:
    """Result of a ForgeLM training run."""
    success: bool
    metrics: Dict[str, float] = field(default_factory=dict)
    final_model_path: Optional[str] = None
    reverted: bool = False
    error: Optional[str] = None
    benchmark_scores: Optional[Dict[str, float]] = None
    benchmark_average: Optional[float] = None
    benchmark_passed: Optional[bool] = None
    resource_usage: Optional[Dict[str, Any]] = None
    safety_passed: Optional[bool] = None
    judge_score: Optional[float] = None
