"""Config v1 -> v2 adds immutable identity, without changing operating settings."""

from typing import Any

CONFIG_VERSION = 2


def migrate_device_data(data: dict[str, Any], version: int, entry_id: str) -> dict[str, Any]:
    if version not in (1, CONFIG_VERSION):
        raise ValueError("unsupported_config_version")
    # Legacy identity comes from the config entry, never the mutable climate entity.
    if version == 1:
        return {**data, "device_id": entry_id}
    device_id = data.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("invalid_device_id")
    return dict(data)
