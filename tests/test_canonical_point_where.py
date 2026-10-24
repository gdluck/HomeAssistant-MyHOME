"""The 4-digit spelling of an area-0 point (``0004``) resolves to the 2-digit form the gateways use (#147, #135)."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from OWNd.message import OWNEvent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome import validate
from custom_components.myhome.const import CONF_PLATFORMS, CONF_WHERE, DOMAIN
from custom_components.myhome.light import async_setup_entry as light_setup_entry
from custom_components.myhome.migrate import migrate_entry_and_registries
from custom_components.myhome.validate import PointToPoint, cover_schema, light_schema
from tests.conftest import attach_runtime

MAC = "00:03:50:00:01:47"


@pytest.fixture(autouse=True)
def _fresh_warnings():
    validate._warned_point_rewrites.clear()
    yield
    validate._warned_point_rewrites.clear()


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ("0004", "04"),
        ("0209", "0209"),
        ("0809", "0809"),
        ("0101", "0101"),
        ("0109", "0109"),
        ("0015", "0015"),
        ("0112", "0112"),
        ("1015", "1015"),
        ("1005", "1005"),
        ("0010", "0010"),
        ("0100", "0100"),
        ("0000", "0000"),
        ("04", "04"),
        ("89", "89"),
    ],
)
def test_point_to_point_canonical_spelling(where: str, expected: str) -> None:
    assert PointToPoint()(where) == expected


def test_one_warning_per_rewritten_address(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            PointToPoint()("0004")
        PointToPoint()("0005")
        PointToPoint()("0015")
        PointToPoint()("0209")
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert "'0004'" in warnings[0] and "'04'" in warnings[0]
    assert "'0005'" in warnings[1] and "'05'" in warnings[1]


def test_yaml_device_keys_use_the_canonical_spelling() -> None:
    lights = light_schema({"kitchen": {CONF_WHERE: "0004", CONF_NAME: "Kitchen"}})
    assert list(lights) == ["1-04"]
    assert lights["1-04"][CONF_WHERE] == "04"
    covers = cover_schema({"blind": {CONF_WHERE: "0005", CONF_NAME: "Blind"}})
    assert covers["2-05"][CONF_WHERE] == "05"


async def test_yaml_light_0004_follows_the_bus_frame_for_04(hass: HomeAssistant) -> None:
    """`where: '0004'` is the light the gateway reports as 04: no duplicate, and its state follows."""
    gateway = MagicMock()
    gateway.mac = MAC
    gateway.log_id = "[test]"
    hass.data = {DOMAIN: {MAC: {"entity": gateway, CONF_PLATFORMS: {"light": light_schema(
        {"kitchen": {CONF_WHERE: "0004", CONF_NAME: "Kitchen"}}
    )}}}}
    config_entry = MagicMock()
    config_entry.data = {"mac": MAC}
    config_entry.entry_id = "test_entry"
    added: list = []
    with patch("custom_components.myhome.discovery.er.async_entries_for_config_entry", return_value=[]), \
         patch("custom_components.myhome.discovery.er.async_get"):
        attach_runtime(hass, config_entry)
        await light_setup_entry(hass, config_entry, added.extend)
    assert len(added) == 1
    light = added[0]
    assert light.unique_id == f"{MAC}-1-04"
    light.async_write_ha_state = MagicMock()
    light.async_schedule_update_ha_state = MagicMock()

    async_dispatcher_send(hass, f"myhome_message_{MAC}", OWNEvent.parse("*1*1*04##"))
    await hass.async_block_till_done()
    assert len(added) == 1  # bus discovery found the configured light, not a new one
    assert light.is_on is True


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="GW", data={CONF_MAC: MAC}, unique_id=MAC, entry_id="e1")
    entry.add_to_hass(hass)
    return entry


def test_registry_moves_0004_to_04_and_merges_the_bus_duplicate(hass: HomeAssistant, config_entry) -> None:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    yaml_dev = dev_reg.async_get_or_create(config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, f"{MAC}-1-0004")})
    bus_dev = dev_reg.async_get_or_create(config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, f"{MAC}-1-04")})
    yaml_light = ent_reg.async_get_or_create(
        "light", DOMAIN, f"{MAC}-1-0004", config_entry=config_entry, device_id=yaml_dev.id, suggested_object_id="kitchen"
    )
    yaml_button = ent_reg.async_get_or_create(
        "button", DOMAIN, f"{MAC}-1-0004-disable", config_entry=config_entry, device_id=yaml_dev.id
    )
    bus_light = ent_reg.async_get_or_create(
        "light", DOMAIN, f"{MAC}-1-04", config_entry=config_entry, device_id=bus_dev.id, suggested_object_id="light_04"
    )
    # A sensor bus discovery hung on its device: no point address of its own, so it is handed over.
    bus_sensor = ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{MAC}-1-04-illuminance", config_entry=config_entry, device_id=bus_dev.id
    )
    keep = ent_reg.async_get_or_create("light", DOMAIN, f"{MAC}-1-0015", config_entry=config_entry)

    migrate_entry_and_registries(hass, config_entry, {})

    assert ent_reg.async_get(bus_light.entity_id) is None
    assert ent_reg.async_get(bus_sensor.entity_id).device_id == yaml_dev.id
    moved = ent_reg.async_get(yaml_light.entity_id)
    assert moved is not None and moved.unique_id == f"{MAC}-1-04"
    assert moved.entity_id == "light.kitchen"
    assert ent_reg.async_get(yaml_button.entity_id).unique_id == f"{MAC}-1-04-disable"
    assert ent_reg.async_get(keep.entity_id).unique_id == f"{MAC}-1-0015"
    assert dev_reg.async_get(bus_dev.id) is None
    device = dev_reg.async_get(yaml_dev.id)
    assert device.identifiers == {(DOMAIN, f"{MAC}-1-04")}
    assert moved.device_id == yaml_dev.id


def test_registry_without_duplicate_is_renamed(hass: HomeAssistant, config_entry, caplog) -> None:
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, f"{MAC}-2-0009#4#01")})
    cover = ent_reg.async_get_or_create(
        "cover", DOMAIN, f"{MAC}-2-0009#4#01", config_entry=config_entry, device_id=device.id
    )
    with caplog.at_level(logging.WARNING):
        migrate_entry_and_registries(hass, config_entry, {})
    assert ent_reg.async_get(cover.entity_id).unique_id == f"{MAC}-2-09#4#01"
    assert dev_reg.async_get(device.id).identifiers == {(DOMAIN, f"{MAC}-2-09#4#01")}
    assert sum("'0009'" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING) == 1


def test_registry_errors_are_logged_and_do_not_block_the_setup(hass: HomeAssistant, config_entry, caplog) -> None:
    """A registry refusal (another entity or device already holds the id) is a WARNING, not a failed setup."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, f"{MAC}-1-0004")})
    light = ent_reg.async_get_or_create("light", DOMAIN, f"{MAC}-1-0004", config_entry=config_entry, device_id=device.id)
    with caplog.at_level(logging.WARNING), \
         patch.object(er.EntityRegistry, "async_update_entity", side_effect=ValueError("id taken")), \
         patch.object(dr.DeviceRegistry, "async_update_device", side_effect=ValueError("id taken")):
        migrate_entry_and_registries(hass, config_entry, {})
    assert ent_reg.async_get(light.entity_id).unique_id == f"{MAC}-1-0004"
    assert dev_reg.async_get(device.id).identifiers == {(DOMAIN, f"{MAC}-1-0004")}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert f"Could not migrate {light.entity_id} to unique_id {MAC}-1-04: id taken" in warnings
    assert f"Could not migrate device {device.id} to the canonical address: id taken" in warnings
