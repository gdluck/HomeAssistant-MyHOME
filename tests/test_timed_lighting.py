"""Tests for OpenWebNet native hardware bus timers (WHO=1).

Verifies build_timed_turn_on_command, MyHOMELight.async_turn_on_timed,
MyHOMESwitch.async_turn_on_timed, and kwarg interception in async_turn_on.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.myhome.const import (
    DOMAIN,
    SERVICE_TURN_ON_TIMED,
    build_timed_turn_on_command,
)
from custom_components.myhome.light import MyHOMELight
from custom_components.myhome.switch import MyHOMESwitch

# ── 1. build_timed_turn_on_command Tests ─────────────────────────────────────

class TestBuildTimedTurnOnCommand:
    """Test frame generation for preset and custom SCS hardware timers."""

    @pytest.mark.parametrize(
        ("seconds", "expected_what"),
        [
            (0.5, 18),
            (30.0, 17),
            (60.0, 11),
            (120.0, 12),
            (180.0, 13),
            (240.0, 14),
            (300.0, 15),
            (900.0, 16),
        ],
    )
    def test_preset_durations(self, seconds, expected_what):
        """Verify all standard Legrand preset timer WHAT codes."""
        cmd = build_timed_turn_on_command("21", duration=seconds)
        assert str(cmd) == f"*1*{expected_what}*21##"

    def test_custom_dimension_2_durations(self):
        """Verify Dimension 2 writing (*#1*WHERE*#2*H*M*S##) for arbitrary durations."""
        # 45 seconds (0h, 0m, 45s)
        cmd45 = build_timed_turn_on_command("21", duration=45)
        assert str(cmd45) == "*#1*21*#2*0*0*45##"

        # 75 seconds (0h, 1m, 15s)
        cmd75 = build_timed_turn_on_command("21", duration=75)
        assert str(cmd75) == "*#1*21*#2*0*1*15##"

        # 3665 seconds (1h, 1m, 5s)
        cmd3665 = build_timed_turn_on_command("21", duration=3665)
        assert str(cmd3665) == "*#1*21*#2*1*1*5##"

        # Compound arguments: hours=2, minutes=15, seconds=30
        cmd_compound = build_timed_turn_on_command("21", hours=2, minutes=15, seconds=30)
        assert str(cmd_compound) == "*#1*21*#2*2*15*30##"

    def test_durations_below_the_shortest_preset_use_it(self):
        """0 < duration < 0.5 s must not become a 0 h 0 m 0 s dimension-2 timer."""
        assert str(build_timed_turn_on_command("11", duration=0.3)) == "*1*18*11##"
        assert str(build_timed_turn_on_command("11", seconds=0.2)) == "*1*18*11##"

    def test_zero_and_negative_duration_defaults_to_half_second(self):
        """Zero or negative duration should safely fall back to 0.5s pulse."""
        cmd_zero = build_timed_turn_on_command("21", duration=0)
        assert str(cmd_zero) == "*1*18*21##"

        cmd_neg = build_timed_turn_on_command("21", duration=-10)
        assert str(cmd_neg) == "*1*18*21##"

        cmd_none = build_timed_turn_on_command("21")
        assert str(cmd_none) == "*1*18*21##"

    def test_private_bus_interface_routing_preserved(self):
        """Private SCS bus routing (#4#INTERFACE) must be preserved in frames."""
        # Preset on bus
        cmd_bus_preset = build_timed_turn_on_command("21#4#01", duration=60)
        assert str(cmd_bus_preset) == "*1*11*21#4#01##"

        # Custom on bus
        cmd_bus_custom = build_timed_turn_on_command("21#4#01", duration=45)
        assert str(cmd_bus_custom) == "*#1*21#4#01*#2*0*0*45##"

        # 4-digit address on bus 02
        cmd_bus_4digit = build_timed_turn_on_command("0311#4#02", hours=1)
        assert str(cmd_bus_4digit) == "*#1*0311#4#02*#2*1*0*0##"

    def test_clamping_ranges(self):
        """Verify hours are clamped to 255, minutes to 59, seconds to 59."""
        cmd_huge = build_timed_turn_on_command("21", hours=300, minutes=90, seconds=90)
        assert str(cmd_huge).startswith("*#1*21*#2*255*")


# ── 2. MyHOMELight Timed Turn-on Tests ────────────────────────────────────────

class TestLightTimedTurnOn:
    """Test MyHOMELight timed operation."""

    @pytest.fixture
    def mock_gateway(self):
        gateway = MagicMock()
        gateway.mac = "AA:BB:CC:DD:EE:FF"
        gateway.send = AsyncMock()
        gateway.send_status_request = AsyncMock()
        gateway.availability_signal = "myhome_avail"
        return gateway

    @pytest.fixture
    def dimmable_light(self, hass, mock_gateway):
        light = MyHOMELight(
            hass=hass,
            name="Test Dimmable",
            entity_name=None,
            icon=None,
            icon_on=None,
            device_id="21",
            who="1",
            where="21",
            interface=None,
            dimmable=True,
            manufacturer="BTicino",
            model="Dimmer",
            gateway=mock_gateway,
        )
        light.hass = hass
        light.async_write_ha_state = MagicMock()
        return light

    @pytest.fixture
    def non_dimmable_light(self, hass, mock_gateway):
        light = MyHOMELight(
            hass=hass,
            name="Test Relay",
            entity_name=None,
            icon=None,
            icon_on=None,
            device_id="22",
            who="1",
            where="22",
            interface=None,
            dimmable=False,
            manufacturer="BTicino",
            model="Relay",
            gateway=mock_gateway,
        )
        light.hass = hass
        light.async_write_ha_state = MagicMock()
        return light

    async def test_async_turn_on_timed_preset(self, dimmable_light, mock_gateway):
        """Test direct async_turn_on_timed with preset duration."""
        await dimmable_light.async_turn_on_timed(duration=60)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*1*11*21##"
        assert dimmable_light.is_on is True
        dimmable_light.async_write_ha_state.assert_called_once()

    async def test_async_turn_on_timed_custom(self, dimmable_light, mock_gateway):
        """Test direct async_turn_on_timed with custom duration."""
        await dimmable_light.async_turn_on_timed(duration=45)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*#1*21*#2*0*0*45##"
        assert dimmable_light.is_on is True

    async def test_async_turn_on_timed_with_brightness(self, dimmable_light, mock_gateway):
        """Test async_turn_on_timed with explicit brightness level."""
        await dimmable_light.async_turn_on_timed(duration=120, brightness=128)

        assert mock_gateway.send.call_count == 2
        first_cmd = mock_gateway.send.call_args_list[0][0][0]
        second_cmd = mock_gateway.send.call_args_list[1][0][0]
        # 128 / 255 -> 50%
        assert str(first_cmd) == "*#1*21*#1*150*0##"
        assert str(second_cmd) == "*1*12*21##"
        assert dimmable_light.brightness == 128
        assert dimmable_light.is_on is True

    async def test_async_turn_on_timed_with_brightness_pct(self, dimmable_light, mock_gateway):
        """Test async_turn_on_timed with brightness percentage."""
        await dimmable_light.async_turn_on_timed(duration=30, brightness_pct=75)

        assert mock_gateway.send.call_count == 2
        first_cmd = mock_gateway.send.call_args_list[0][0][0]
        second_cmd = mock_gateway.send.call_args_list[1][0][0]

        assert str(first_cmd) == "*#1*21*#1*175*0##"
        assert str(second_cmd) == "*1*17*21##"
        assert dimmable_light.is_on is True

    async def test_async_turn_on_timed_brightness_one_is_on_at_minimum(self, dimmable_light, mock_gateway):
        """brightness 1 of 255 rounds to 0 % but means "on at minimum", not "no level"."""
        await dimmable_light.async_turn_on_timed(duration=120, brightness=1)

        frames = [str(call[0][0]) for call in mock_gateway.send.call_args_list]
        assert frames == ["*#1*21*#1*101*0##", "*1*12*21##"]

    async def test_async_turn_on_timed_non_dimmable_ignores_brightness(self, non_dimmable_light, mock_gateway):
        """Non-dimmable light ignores brightness parameters and only sends timed command."""
        await non_dimmable_light.async_turn_on_timed(duration=60, brightness=200)

        assert mock_gateway.send.call_count == 1
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*1*11*22##"
        assert non_dimmable_light.is_on is True

    async def test_async_turn_on_timer_kwarg(self, dimmable_light, mock_gateway):
        """Test async_turn_on intercepting 'timer' kwarg."""
        await dimmable_light.async_turn_on(timer=300)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*1*15*21##"
        assert dimmable_light.is_on is True

    async def test_async_turn_on_duration_kwarg(self, dimmable_light, mock_gateway):
        """Test async_turn_on intercepting 'duration' kwarg."""
        await dimmable_light.async_turn_on(duration=180)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*1*13*21##"
        assert dimmable_light.is_on is True

    async def test_async_turn_on_timer_and_brightness(self, dimmable_light, mock_gateway):
        """Test async_turn_on with both timer and brightness kwargs."""
        await dimmable_light.async_turn_on(timer=45, brightness=255)

        assert mock_gateway.send.call_count == 2
        first_cmd = mock_gateway.send.call_args_list[0][0][0]
        second_cmd = mock_gateway.send.call_args_list[1][0][0]

        assert str(first_cmd) == "*#1*21*#1*200*0##"
        assert str(second_cmd) == "*#1*21*#2*0*0*45##"


# ── 3. MyHOMESwitch Timed Turn-on Tests ───────────────────────────────────────

class TestSwitchTimedTurnOn:
    """Test MyHOMESwitch timed operation."""

    @pytest.fixture
    def mock_gateway(self):
        gateway = MagicMock()
        gateway.mac = "AA:BB:CC:DD:EE:FF"
        gateway.send = AsyncMock()
        gateway.send_status_request = AsyncMock()
        gateway.availability_signal = "myhome_avail"
        return gateway

    @pytest.fixture
    def test_switch(self, hass, mock_gateway):
        switch = MyHOMESwitch(
            hass=hass,
            name="Test Switch",
            entity_name=None,
            icon=None,
            icon_on=None,
            device_id="31",
            who="1",
            where="31",
            interface=None,
            device_class="switch",
            manufacturer="BTicino",
            model="F411/2",
            gateway=mock_gateway,
        )
        switch.hass = hass
        switch.async_write_ha_state = MagicMock()
        return switch

    async def test_switch_async_turn_on_timed_preset(self, test_switch, mock_gateway):
        """Test direct async_turn_on_timed on switch with preset."""
        await test_switch.async_turn_on_timed(duration=900)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*1*16*31##"
        assert test_switch.is_on is True

    async def test_switch_async_turn_on_timed_accepts_and_ignores_brightness(self, test_switch, mock_gateway):
        """The service schema is shared with lights; a relay takes the fields and sends no level."""
        await test_switch.async_turn_on_timed(duration=60, brightness=200, brightness_pct=50)

        mock_gateway.send.assert_called_once()
        assert str(mock_gateway.send.call_args[0][0]) == "*1*11*31##"

    async def test_switch_async_turn_on_timed_custom(self, test_switch, mock_gateway):
        """Test direct async_turn_on_timed on switch with custom time."""
        await test_switch.async_turn_on_timed(hours=1, minutes=30, seconds=0)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*#1*31*#2*1*30*0##"
        assert test_switch.is_on is True

    async def test_switch_async_turn_on_timer_kwarg(self, test_switch, mock_gateway):
        """Test switch.async_turn_on intercepting 'timer' kwarg."""
        await test_switch.async_turn_on(timer=60)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*1*11*31##"
        assert test_switch.is_on is True

    async def test_switch_async_turn_on_duration_kwarg(self, test_switch, mock_gateway):
        """Test switch.async_turn_on intercepting 'duration' kwarg."""
        await test_switch.async_turn_on(duration=45)

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*#1*31*#2*0*0*45##"
        assert test_switch.is_on is True

    async def test_switch_async_turn_on_normal(self, test_switch, mock_gateway):
        """Standard switch.async_turn_on without timer calls standard switch_on."""
        await test_switch.async_turn_on()

        mock_gateway.send.assert_called_once()
        sent_cmd = mock_gateway.send.call_args[0][0]
        assert str(sent_cmd) == "*1*1*31##"


# ── 4. Service Registration Verification ─────────────────────────────────────

class TestServiceRegistration:
    """myhome.turn_on_timed is one service for both the light and the switch entities."""

    @staticmethod
    def _gateway():
        gateway = MagicMock()
        gateway.mac = "AA:BB:CC:DD:EE:FF"
        gateway.send = AsyncMock()
        gateway.send_status_request = AsyncMock()
        gateway.availability_signal = "myhome_avail"
        gateway.available = True
        return gateway

    @staticmethod
    def _register(hass, domain, entity):
        """Put an entity where EntityPlatform would: the per-domain platform map."""
        from homeassistant.helpers.entity_platform import DATA_DOMAIN_PLATFORM_ENTITIES

        entity.hass = hass
        entity.entity_id = f"{domain}.{entity._where}"
        entity.async_write_ha_state = MagicMock()
        hass.data.setdefault(DATA_DOMAIN_PLATFORM_ENTITIES, {}).setdefault((domain, DOMAIN), {})[entity.entity_id] = entity

    async def test_schema_accepts_the_documented_brightness_fields(self, hass):
        from custom_components.myhome.services import async_setup_services

        await async_setup_services(hass)
        assert hass.services.has_service(DOMAIN, SERVICE_TURN_ON_TIMED)
        schema = hass.services.async_services_for_domain(DOMAIN)[SERVICE_TURN_ON_TIMED].schema
        assert schema({"entity_id": "light.x", "duration": 120, "brightness_pct": 70})["brightness_pct"] == 70
        assert schema({"entity_id": "light.x", "minutes": 3, "seconds": 30, "brightness": 255})["brightness"] == 255

    async def test_service_reaches_lights_and_switches(self, hass):
        """A per-platform registration only ever bound one domain; the other target was a silent no-op."""
        from custom_components.myhome.services import async_setup_services

        gateway = self._gateway()
        light = MyHOMELight(
            hass=hass, name="Hall", entity_name=None, icon=None, icon_on=None, device_id="12", who="1",
            where="12", interface=None, dimmable=True, manufacturer="BTicino", model="Dimmer", gateway=gateway,
        )
        switch = MyHOMESwitch(
            hass=hass, name="Socket", entity_name=None, icon=None, icon_on=None, device_id="22", who="1",
            where="22", interface=None, device_class="switch", manufacturer="BTicino", model="F411/2", gateway=gateway,
        )
        self._register(hass, "light", light)
        self._register(hass, "switch", switch)
        await async_setup_services(hass)

        await hass.services.async_call(
            DOMAIN, SERVICE_TURN_ON_TIMED, {"entity_id": "switch.22", "duration": 1800}, blocking=True
        )
        assert [str(c.args[0]) for c in gateway.send.call_args_list] == ["*#1*22*#2*0*30*0##"]

        gateway.send.reset_mock()
        await hass.services.async_call(
            DOMAIN, SERVICE_TURN_ON_TIMED, {"entity_id": "light.12", "duration": 120, "brightness_pct": 70}, blocking=True
        )
        assert [str(c.args[0]) for c in gateway.send.call_args_list] == ["*#1*12*#1*170*0##", "*1*12*12##"]

        # a switch takes the brightness fields and sends no level
        gateway.send.reset_mock()
        await hass.services.async_call(
            DOMAIN, SERVICE_TURN_ON_TIMED, {"entity_id": "switch.22", "duration": 60, "brightness": 200}, blocking=True
        )
        assert [str(c.args[0]) for c in gateway.send.call_args_list] == ["*1*11*22##"]
