"""Single persisted group registry; publish changes only after a successful save."""

import asyncio
from collections.abc import Callable
from typing import Any

from ..domain.groups import GroupRegistry, restore_registry, serialize_registry


class GroupRepository:
    def __init__(self, store: Any) -> None:
        self.store = store
        self.registry: GroupRegistry | None = None
        self._lock = asyncio.Lock()

    async def async_load(self) -> GroupRegistry:
        async with self._lock:
            if self.registry is None:
                self.registry = restore_registry(await self.store.async_load())
            return self.registry

    async def async_update(self, change: Callable[[GroupRegistry], GroupRegistry]) -> GroupRegistry:
        async with self._lock:
            current = self.registry
            if current is None:
                current = restore_registry(await self.store.async_load())
            updated = change(current)
            await self.store.async_save(serialize_registry(updated))
            self.registry = updated
            return updated


def get_group_repository(hass: Any) -> GroupRepository:
    """One lock/registry per HA instance; standalone setup need not load this store."""
    from homeassistant.helpers.storage import Store

    from ..const import DOMAIN

    key = f"{DOMAIN}.groups"
    if key not in hass.data:
        hass.data[key] = GroupRepository(Store(hass, 1, key))
    repository: GroupRepository = hass.data[key]
    return repository
