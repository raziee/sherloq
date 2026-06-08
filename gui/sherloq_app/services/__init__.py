"""Headless forensic analysis services for web and API use."""

from gui.sherloq_app.services.dispatcher import analyze, list_tools
from gui.sherloq_app.services.results import ServiceResult

__all__ = ["ServiceResult", "analyze", "list_tools"]
