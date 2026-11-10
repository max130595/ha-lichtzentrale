# Geändert für Lichtzentrale
"""Optional Recorder data is useful only with enough genuine daily edges."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.lichtzentrale.vacation_config import default_vacation_config
from custom_components.lichtzentrale.vacation_history import (
    async_learn_history,
    learn_typical_times,
)

ZONE = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 9, 12, tzinfo=ZONE)
ENTITY = "light.synthetic_history"


def edges(days=4, minute=18 * 60):
    result = []
    for offset in range(days, 0, -1):
        when = (NOW - timedelta(days=offset)).replace(hour=minute // 60, minute=minute % 60)
        result.extend([State(ENTITY, "off", last_changed=when - timedelta(minutes=1)),
                       State(ENTITY, "on", last_changed=when),
                       State(ENTITY, "on", {"brightness": 120}, last_changed=when + timedelta(seconds=10))])
    return result


def test_learned_typical_and_fallback():
    dt_util.set_default_time_zone(ZONE)
    assert learn_typical_times({ENTITY: edges()}, {"test_room": [ENTITY]}, NOW) == {"test_room": 1080}
    assert learn_typical_times({ENTITY: edges(2)}, {"test_room": [ENTITY]}, NOW) == {}
    assert learn_typical_times({}, {"test_room": [ENTITY]}, NOW) == {}
    assert learn_typical_times({ENTITY: edges()[1:2]}, {"test_room": [ENTITY]}, NOW) == {}
    assert learn_typical_times({ENTITY: edges()}, {"test_room": [ENTITY]}, NOW + timedelta(days=20)) == {}


def test_repeated_updates_do_not_count_as_multiple_days():
    when = NOW - timedelta(days=1)
    history = [State(ENTITY, "off" if index % 2 == 0 else "on", last_changed=when + timedelta(minutes=index))
               for index in range(20)]
    assert learn_typical_times({ENTITY: history}, {"test_room": [ENTITY]}, NOW) == {}


async def test_recorder_absent_or_disabled(hass, store):
    config = default_vacation_config()
    config["learn_history"] = True
    assert await async_learn_history(hass, store, config, NOW) == {}
    hass.config.components.add("recorder")
    config["learn_history"] = False
    assert await async_learn_history(hass, store, config, NOW) == {}


async def test_recorder_executor_query_and_failure(hass, store):
    dt_util.set_default_time_zone(ZONE)
    hass.config.components.add("recorder")
    config = default_vacation_config()
    config.update(learn_history=True, rooms=[{"area_id": "test_room", "weight": 1}])

    async def executor(function):
        return function()

    instance = Mock(async_add_executor_job=AsyncMock(side_effect=executor))
    with patch("custom_components.lichtzentrale.rooms.room_targets", return_value=[ENTITY]), patch(
        "homeassistant.components.recorder.get_instance", return_value=instance
    ), patch("homeassistant.components.recorder.history.get_significant_states", return_value={ENTITY: edges()}) as query:
        assert await async_learn_history(hass, store, config, NOW) == {"test_room": 1080}
        assert query.call_args.args[1] == dt_util.as_utc(NOW) - timedelta(days=14)
        assert query.call_args.kwargs["entity_ids"] == [ENTITY]
        query.side_effect = RuntimeError("Recorder unavailable")
        assert await async_learn_history(hass, store, config, NOW) == {}
