from dataclasses import dataclass
from typing import Any, Callable

from gui.sherloq_app.services.results import ServiceResult


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    group: str
    description: str
    handler: Callable[..., ServiceResult]
    requires_file: bool = False
    async_default: bool = False
    parameters: dict[str, Any] | None = None


TOOL_REGISTRY: list[ToolSpec] = []
