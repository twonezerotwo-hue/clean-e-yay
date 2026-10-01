"""Evidence-only probabilistic forecast helpers.

The forecast layer produces bounded price bands from already verified snapshot
inputs.  It never creates an order, changes a decision, or treats a point
estimate as a promise.
"""

from packages.forecast.bands import ForecastBand, build_forecasts

__all__ = ["ForecastBand", "build_forecasts"]
