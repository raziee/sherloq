from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ServiceResult:
    """Structured output from a forensic analysis service."""

    data: dict[str, Any] = field(default_factory=dict)
    images: dict[str, np.ndarray] = field(default_factory=dict)

    def merge(self, other: "ServiceResult") -> "ServiceResult":
        merged = ServiceResult()
        merged.data = {**self.data, **other.data}
        merged.images = {**self.images, **other.images}
        return merged
