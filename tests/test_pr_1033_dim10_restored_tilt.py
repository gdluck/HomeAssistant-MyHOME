"""Regression tests for PR #1033 N1: Dim 10 Venetian blind restored tilt + height across restart."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.restore_state import RestoredExtraData
from OWNd.message import OWNEvent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome.const import DOMAIN
from custom_components.myhome.cover import MyHOMECover
from custom_components.myhome.data import MyHOMERuntimeData
from custom_components.myhome.gateway import MyHOMEGatewayHandler

MAC = "00:03:50:aa:33:10"
# Real F454 + F401 stopped Dimension 10 frame (index 40 of
# tests/fixtures/traces/discussion_770_f454_f401/myhome_trace_F454_all_2026-10-23T11-11-26.json).
DIM10_STOPPED_AT_0 = "*#2*21*10*10*0*001*15##"
# Real F454 + F401 stopped Dimension 10 frame (index 2 of the same trace).
DIM10_STOPPED_AT_2 = "*#2*21*10*10*2*001*15##"


def _make_cover(hass: HomeAssistant) -> MyHOMECover:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.0.2.34",
            CONF_PORT: 20000,
            CONF_PASSWORD: "secret",
            CONF_MAC: MAC,
            CONF_NAME: "F454",
        },
        options={},
        unique_id=MAC,
    )
    entry.add_to_hass(hass)
    handler = MyHOMEGatewayHandler(hass, entry)
    handler.send = AsyncMock()
    handler.send_status_request = AsyncMock()
    entry.runtime_data = MyHOMERuntimeData(gateway=handler)

    cov = MyHOMECover(
        hass=hass,
        name="Venetian 21",
        entity_name=None,
        device_id="21",
        who="2",
        where="21",
        interface=None,
        device_class=None,
        manufacturer="BTicino",
        model="F401",
        gateway=handler,
        advanced=True,
        slat_tilt=True,
        slat_time=2.0,
    )
    cov.entity_id = "cover.venetian_21"
    cov.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    return cov


async def test_dim10_restored_tilt_kept_when_first_poll_matches_saved_level(
    hass: HomeAssistant,
) -> None:
    """Restored slat tilt survives the first stopped Dim 10 frame when curtain height is unchanged."""
    cov_before = _make_cover(hass)
    cov_before._attr_current_cover_position = 0
    cov_before._attr_current_cover_tilt_position = 65
    extra = cov_before.extra_restore_state_data
    assert extra is not None
    assert extra.as_dict()["tilt"] == 65
    assert extra.as_dict()["tilt_level"] == 0

    cov = _make_cover(hass)
    cov.async_get_last_extra_data = AsyncMock(return_value=RestoredExtraData(extra.as_dict()))  # type: ignore[method-assign]
    await cov.async_restore_last_state(
        State("cover.venetian_21", "closed", {"current_position": 0, "current_tilt_position": 65})
    )
    assert cov.current_cover_tilt_position == 65

    cov.handle_event(OWNEvent.parse(DIM10_STOPPED_AT_0))
    assert cov.current_cover_position == 0
    assert cov.current_cover_tilt_position == 65


async def test_dim10_restored_tilt_from_unavailable_kept_at_same_level(
    hass: HomeAssistant,
) -> None:
    """Restoring from STATE_UNAVAILABLE uses extra_restore_state_data tilt_level too."""
    cov = _make_cover(hass)
    cov.async_get_last_extra_data = AsyncMock(  # type: ignore[method-assign]
        return_value=RestoredExtraData({"tilt": 65, "tilt_level": 0})
    )
    await cov.async_restore_last_state(State("cover.venetian_21", STATE_UNAVAILABLE, {}))
    assert cov.current_cover_tilt_position == 65

    cov.handle_event(OWNEvent.parse(DIM10_STOPPED_AT_0))
    assert cov.current_cover_position == 0
    assert cov.current_cover_tilt_position == 65


async def test_dim10_restored_tilt_turns_when_curtain_moved_while_ha_was_down(
    hass: HomeAssistant,
) -> None:
    """If curtain height changed while HA was down, the first Dim 10 frame turns slats accordingly."""
    # Case 1: restore runs before the first Dim 10 frame (curtain lowered from 50 -> 0)
    cov_down = _make_cover(hass)
    cov_down.async_get_last_extra_data = AsyncMock(  # type: ignore[method-assign]
        return_value=RestoredExtraData({"tilt": 65, "tilt_level": 50})
    )
    await cov_down.async_restore_last_state(
        State("cover.venetian_21", "open", {"current_position": 50, "current_tilt_position": 65})
    )
    cov_down.handle_event(OWNEvent.parse(DIM10_STOPPED_AT_0))
    assert cov_down.current_cover_position == 0
    assert cov_down.current_cover_tilt_position == 0

    # Case 2: restore runs before the first Dim 10 frame (curtain raised from 0 -> 2)
    cov_up = _make_cover(hass)
    cov_up.async_get_last_extra_data = AsyncMock(  # type: ignore[method-assign]
        return_value=RestoredExtraData({"tilt": 35, "tilt_level": 0})
    )
    await cov_up.async_restore_last_state(
        State("cover.venetian_21", "closed", {"current_position": 0, "current_tilt_position": 35})
    )
    cov_up.handle_event(OWNEvent.parse(DIM10_STOPPED_AT_2))
    assert cov_up.current_cover_position == 2
    assert cov_up.current_cover_tilt_position == 100

    # Case 3: first Dim 10 frame (at 0) arrived before restore while saved height was 50 -> slats stay 0
    cov_race = _make_cover(hass)
    cov_race.handle_event(OWNEvent.parse(DIM10_STOPPED_AT_0))
    assert cov_race.current_cover_position == 0
    assert cov_race.current_cover_tilt_position == 0
    cov_race.async_get_last_extra_data = AsyncMock(  # type: ignore[method-assign]
        return_value=RestoredExtraData({"tilt": 65, "tilt_level": 50})
    )
    await cov_race.async_restore_last_state(
        State("cover.venetian_21", "open", {"current_position": 50, "current_tilt_position": 65})
    )
    assert cov_race.current_cover_tilt_position == 0


async def test_dim10_first_end_poll_still_assumes_end_tilt_without_restore(
    hass: HomeAssistant,
) -> None:
    """Without restored tilt, a first stopped Dim 10 frame at an end still assumes end tilt."""
    cov = _make_cover(hass)
    cov.handle_event(OWNEvent.parse(DIM10_STOPPED_AT_0))
    assert cov.current_cover_position == 0
    assert cov.current_cover_tilt_position == 0
    assert cov._tilt_assumed_from_end is True
