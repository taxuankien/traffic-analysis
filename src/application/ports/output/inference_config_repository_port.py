"""Output port cho việc đọc/ghi inference config.

Tách interface khỏi adapter cụ thể để application không phụ thuộc YAML
implementation, đồng thời cho phép web layer ``PUT /api/config/inference``
ghi file an toàn (atomic write) mà không leak ``pyyaml``/``ruamel.yaml``
vào application services.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.bootstrap.inference_config import InferenceConfig


class InferenceConfigRepositoryPort(ABC):
    @abstractmethod
    def load(self) -> InferenceConfig:
        """Đọc config hiện tại; raise ``FileNotFoundError`` nếu không có file."""

    @abstractmethod
    def save(self, config: InferenceConfig) -> None:
        """Ghi config xuống storage. Phải atomic: nếu fail giữa chừng,
        file đích phải còn ở trạng thái valid (không corrupt).
        """

    @abstractmethod
    def reset_to_defaults(self) -> InferenceConfig:
        """Ghi đè bằng default snapshot (hardcoded trong ``InferenceConfig``)
        rồi trả về config mới. Dùng cho endpoint ``POST /reset``.
        """
