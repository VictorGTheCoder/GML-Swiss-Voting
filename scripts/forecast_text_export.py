"""Compatibility import for the publication-aware brochure text exporter.

The temporal eligibility implementation lives with the federal-explanations
domain module. Keep this evaluation-facing path as a thin API alias.
"""

from scripts.federal_explanations.federal_explanations_temporal import build_forecast_text_export

__all__ = ["build_forecast_text_export"]
