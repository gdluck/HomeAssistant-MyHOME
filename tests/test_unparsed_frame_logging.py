"""Frames OWNd cannot parse are logged once per shape at WARNING, then at DEBUG (#139)."""
import logging
from unittest.mock import MagicMock

import pytest

from custom_components.myhome.gateway import MyHOMEGatewayHandler


@pytest.fixture
def gateway_handler():
    entry = MagicMock()
    entry.entry_id = "entry_unparsed"
    entry.data = {
        "host": "192.168.1.5",
        "port": 20000,
        "password": "12345",
        "mac": "00:03:50:00:00:01",
        "name": "F461",
        "manufacturer": "BTicino",
        "firmware": "2.0.11",
    }
    entry.options = {}
    entry.title = "F461 Gateway"
    hass = MagicMock()
    hass.data = {}
    return MyHOMEGatewayHandler(hass, entry)


def _not_a_message(caplog, level):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == level and "Data received is not a message" in r.getMessage()
    ]


async def test_unparsed_frame_warns_once_per_shape(gateway_handler, caplog):
    """A zone thermostat pushing `*#4*#1*14*#0230*1##` every few seconds yields one WARNING, not a flood."""
    with caplog.at_level(logging.DEBUG, logger="custom_components.myhome"):
        for frame in ("*#4*#1*14*#0230*1##", "*#4*#1*14*#0231*1##", "*#4*#2*14*#0205*1##"):
            await gateway_handler._process_message(frame)
        await gateway_handler._process_message("*#13**27*F461##")

    warnings = _not_a_message(caplog, logging.WARNING)
    assert len(warnings) == 2, warnings
    assert "*#4*#1*14*#0230*1##" in warnings[0]
    assert "*#13**27*F461##" in warnings[1]
    # The repeats are still visible at DEBUG for troubleshooting
    assert len(_not_a_message(caplog, logging.DEBUG)) == 2
