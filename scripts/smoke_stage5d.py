# Geändert für Lichtzentrale
"""Native HA 2026.11 dimming regression, without devices or pytest shims.

Run: .venv-target/bin/python scripts/smoke_stage5d.py
Exercises the real HA light service handler and rounding on synthetic entities.
"""
import asyncio
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import homeassistant  # noqa: F401
from homeassistant.components.light import ColorMode, LightEntity, LightEntityFeature, Profiles
from homeassistant.components.light.const import DATA_PROFILES
from homeassistant.components.light.services import _async_handle_light_on_service
from homeassistant.core import HomeAssistant, ServiceCall, State

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.lichtzentrale.dimming import dim_payload
from custom_components.lichtzentrale.rooms import async_dispatch


class SyntheticLight(LightEntity):
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_is_on = True
    _attr_brightness = 128
    _attr_supported_features = LightEntityFeature(0)
    entity_id = 'light.synthetic_dim'

    def __init__(self, hass):
        self.hass = hass
        self.off_calls = 0
        self.on_calls = 0

    async def async_turn_on(self, **kwargs):
        self.on_calls += 1
        self._attr_brightness = kwargs['brightness']
        self._attr_is_on = True

    async def async_turn_off(self, **kwargs):
        self.off_calls += 1
        self._attr_is_on = False

    def snapshot(self):
        return State(self.entity_id, 'on' if self.is_on else 'off', {
            'supported_color_modes': ['brightness'], 'brightness': self.brightness,
        })


async def run(directory):
    hass = HomeAssistant(directory)
    hass.data[DATA_PROFILES] = Profiles(hass)
    light = SyntheticLight(hass)
    try:
        async def native(call):
            params = {k: v for k, v in call.data.items() if k != 'entity_id'}
            await _async_handle_light_on_service(light, ServiceCall(hass, 'light', 'turn_on', {'params': params}))
        hass.services.async_register('light', 'turn_on', native)
        for pct in range(1, 21):
            floor = round(pct * 255 / 100)
            for brightness in range(1, 256):
                light._attr_brightness = brightness
                payload = dim_payload(light.snapshot(), -1, pct)
                if payload is not None:
                    await hass.services.async_call('light', 'turn_on', payload, blocking=True)
                    assert floor <= light.brightness <= brightness
                else:
                    assert brightness <= floor
                assert light.off_calls == 0
        # Planning at 50%, then lowering before our final dispatch.
        light._attr_brightness = 128
        params = dim_payload(light.snapshot(), -1, 1)
        light._attr_brightness = 13
        def guard(entity_id):
            fresh = dim_payload(light.snapshot(), -1, 1)
            if fresh is None:
                return False
            params.clear()
            params.update(fresh)
            return True
        result = await async_dispatch(hass, [('light', 'turn_on', params)], guard=guard)
        assert result['applied'] == [light.entity_id]
        assert light.brightness == 3 and light.off_calls == 0
        # Holding at the lower bound sends no further command.
        before = light.on_calls
        result = await async_dispatch(hass, [('light', 'turn_on', params)], guard=guard)
        assert result['skipped'] == [light.entity_id] and light.on_calls == before
        # Explicit off stays an ordinary native off.
        await light.async_turn_off()
        assert not light.is_on and light.off_calls == 1
    finally:
        await hass.async_stop(force=True)


if __name__ == '__main__':
    assert version('homeassistant') == '2026.11.0'
    with TemporaryDirectory(prefix='lichtzentrale-dimming-') as directory:
        asyncio.run(run(directory))
    print('PASS: native HA 2026.11.0, 5,100 brightness/floor cases, dispatch race and repeat boundary; no devices.')
