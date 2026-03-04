from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from integrations.adapters.base import AbstractChannelAdapter
    from integrations.models import ChannelLink


class AdapterRegistry:
    """Import, cache, and instantiate channel adapters by dotted path."""

    _cache: dict[str, type[AbstractChannelAdapter]] = {}

    @classmethod
    def get_adapter_class(cls, dotted_path: str) -> type[AbstractChannelAdapter]:
        if dotted_path in cls._cache:
            return cls._cache[dotted_path]

        from integrations.adapters.base import AbstractChannelAdapter

        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        klass = getattr(module, class_name)

        if not issubclass(klass, AbstractChannelAdapter):
            raise TypeError(
                f"{dotted_path} is not a subclass of AbstractChannelAdapter"
            )

        cls._cache[dotted_path] = klass
        return klass

    @classmethod
    def get_adapter(cls, channel_link: ChannelLink) -> AbstractChannelAdapter:
        klass = cls.get_adapter_class(channel_link.channel.adapter_class)
        return klass(channel_link)

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
