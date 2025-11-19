"""
Competition execution and monitoring module.

This module provides intelligent scheduling, containerized agent runtime,
and adaptive monitoring for autonomous trading competitions.
"""

from .scheduler import CompetitionScheduler, SchedulingDecision
from .ai_optimizer import AICompetitionOptimizer, MarketSignal
from .event_triggers import EventTriggerManager, TriggerEvent, TriggerType

__all__ = [
    'CompetitionScheduler',
    'SchedulingDecision',
    'AICompetitionOptimizer',
    'MarketSignal',
    'EventTriggerManager',
    'TriggerEvent',
    'TriggerType'
]