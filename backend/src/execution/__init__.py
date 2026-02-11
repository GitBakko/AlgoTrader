"""
Execution module.
Provides order management, position tracking, slippage monitoring,
and the unified execution engine.
"""

from src.execution.execution_engine import ExecutionEngine
from src.execution.order_manager import OrderManager
from src.execution.position_tracker import PositionTracker
from src.execution.schemas import ExecutionMode, ExecutionOrder, ExecutionResult
from src.execution.slippage_tracker import SlippageTracker

__all__ = [
    "ExecutionEngine",
    "ExecutionMode",
    "ExecutionOrder",
    "ExecutionResult",
    "OrderManager",
    "PositionTracker",
    "SlippageTracker",
]
