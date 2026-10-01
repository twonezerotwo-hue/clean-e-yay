"""Evidence-calibrated scenario distribution; observation-only."""

from packages.scenarios.engine import build_report
from packages.scenarios.model import ScenarioReport, ScenarioResult

__all__ = ["ScenarioReport", "ScenarioResult", "build_report"]
