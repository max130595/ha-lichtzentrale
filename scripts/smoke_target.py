"""Native HA compatibility smoke test, not a replacement for the pytest suite.

Run with the target Home Assistant installed:
    python scripts/smoke_target.py

No pytest fixtures, HA private-symbol shims, network listeners, or external devices.
Real Store files live only inside a temporary directory deleted after this run.
"""

from __future__ import annotations

import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

# Import HA before anything that may import httpx: HA 2026.11 installs its
# supported httpx2 alias during package initialization.
import homeassistant  # noqa: F401
from homeassistant.components.light import LightEntityFeature
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry, device_registry, entity_registry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.lichtzentrale import (  # noqa: E402
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.lichtzentrale.config_flow import LichtzentraleConfigFlow  # noqa: E402
from custom_components.lichtzentrale.const import STORAGE_KEY  # noqa: E402
from custom_components.lichtzentrale.lights import list_lights, validate_lights  # noqa: E402
from custom_components.lichtzentrale.palettes import async_apply_palette, list_palettes  # noqa: E402
from custom_components.lichtzentrale.storage import LichtzentraleStore  # noqa: E402
from custom_components.lichtzentrale.websocket_api import APPLY_FIELDS  # noqa: E402


async def run(config_dir: str) -> None:
    """Exercise real native objects without bootstrapping network integrations."""
    hass = HomeAssistant(config_dir)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    try:
        await area_registry.async_load(hass)
        device_registry.async_setup(hass)
        await device_registry.async_load(hass)
        await entity_registry.async_load(hass)
        assert callable(async_setup_entry)
        assert callable(async_unload_entry)
        assert callable(async_remove_entry)
        assert LichtzentraleConfigFlow.VERSION == 1
        assert APPLY_FIELDS

        store = LichtzentraleStore(hass)
        await store.async_load()
        assert store.data["settings"]["light_entity_ids"] == []
        path = Path(config_dir) / ".storage" / STORAGE_KEY
        assert path.is_file()
        assert json.loads(path.read_text())["version"] == 1

        calls = []

        @callback
        def capture(call):
            calls.append(call)

        hass.services.async_register("light", "turn_on", capture)
        modes = ["xy", "rgbww", "color_temp", "brightness", "onoff"]
        targets = []
        for index, mode in enumerate(modes):
            entity_id = f"light.fixture_{index}"
            targets.append(entity_id)
            hass.states.async_set(
                entity_id,
                "off",
                {
                    "supported_color_modes": [mode],
                    "supported_features": LightEntityFeature.TRANSITION,
                    # A deliberately narrow CT range verifies clamping.
                    "min_color_temp_kelvin": 3999,
                    "max_color_temp_kelvin": 4000,
                },
            )
        hass.states.async_set(
            "light.fixture_unavailable", "unavailable", {"supported_color_modes": ["xy"]}
        )
        targets.append("light.fixture_unavailable")
        await store.async_set_lights(targets)
        restored = LichtzentraleStore(hass)
        await restored.async_load()
        assert restored.data == store.data
        assert len(list_lights(hass, targets)) == 6

        palettes = list_palettes()
        assert len(palettes) == 12
        assert len({item["category"] for item in palettes}) == 4
        result = await async_apply_palette(hass, restored, palettes[0]["id"], targets, 123)
        assert result == {"applied": targets[:-1], "skipped": ["light.fixture_unavailable"]}
        assert len(calls) == 5
        assert "xy_color" in calls[0].data
        assert "xy_color" in calls[1].data
        assert 3999 <= calls[2].data["color_temp_kelvin"] <= 4000
        assert calls[3].data["brightness"] == 123
        assert "xy_color" not in calls[3].data
        assert "brightness" not in calls[4].data
        assert all(call.data["transition"] == 1 for call in calls)

        for forbidden in ("switch.fixture_a", "lock.fixture_a", "light.fixture_group"):
            hass.states.async_set(forbidden, "on", {"is_hue_group": True})
            try:
                validate_lights(hass, [targets[0], forbidden])
            except ServiceValidationError:
                pass
            else:
                raise AssertionError(f"Unsafe target accepted: {forbidden}")
        hass.states.async_set("light.fixture_unapproved", "on", {"supported_color_modes": ["xy"]})
        try:
            await async_apply_palette(
                hass, restored, palettes[0]["id"], ["light.fixture_unapproved"]
            )
        except ServiceValidationError:
            pass
        else:
            raise AssertionError("Unapproved lamp accepted")
        assert len(calls) == 5
        await restored.async_remove()
        assert not path.exists()
    finally:
        await hass.async_stop(force=True)


def main() -> None:
    """Report exact runtime and explicitly bounded verification scope."""
    with TemporaryDirectory(prefix="lichtzentrale-smoke-") as config_dir:
        asyncio.run(run(config_dir))
    print(f"PASS native smoke: Home Assistant {version('homeassistant')}")
    print(
        "Verified: integration imports; native registries/discovery; real Store create, "
        "reload and removal; 12 palettes/4 categories; XY, RGBWW, CT clamp, brightness, "
        "on/off; unavailable skip; allowlist and switch/lock/group rejection; service dispatch."
    )
    print(
        "Not verified here: full config-entry/panel lifecycle, HTTP/WebSocket protocol, "
        "frontend rendering or physical devices. These are separate test scopes."
    )


if __name__ == "__main__":
    main()
