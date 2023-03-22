#!/usr/bin/env python3
#
# Filename: consts.py
#
# Author: Simon Redman <simon@ergotech.com>
# File Created: 01.03.2023
# Last Modified: Sat 25 Feb 2023 08:38:58 PM EST
# Description: Constants used within the ember-mqtt-bridge project
#

from typing import Dict, NamedTuple

SUTA_MANUFACTURER = "suta"

class MqttPayload(NamedTuple):
    topic: str
    payload: Dict[str, str]
    retain: bool = True
