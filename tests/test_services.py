# Geändert für Lichtzentrale
"""Service descriptions must survive Home Assistant's YAML 1.1 parser."""

from pathlib import Path

from homeassistant.util.yaml import load_yaml


def test_service_field_keys_remain_strings():
    path = Path(__file__).resolve().parents[1] / "custom_components/lichtzentrale/services.yaml"
    descriptions = load_yaml(str(path))
    assert set(descriptions) == {"apply_palette", "apply_scene", "toggle_room", "stop_dynamic", "set_adaptive", "next_scene"}
    for description in descriptions.values():
        assert all(isinstance(key, str) for key in description["fields"])
    assert "on" in descriptions["toggle_room"]["fields"]
    assert descriptions["toggle_room"]["fields"]["on"]["selector"] == {"boolean": None}
