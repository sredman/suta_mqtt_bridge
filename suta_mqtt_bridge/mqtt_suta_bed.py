#!/usr/bin/env python3
#
# Filename: mqtt_suta_bed.py
#
# Author: Simon Redman <simon@ergotech.com>
# File Created: 03.21.2023
# Description: Handle BLE communications and MQTT objects for a SUTA bed frame
#

import asyncio

from suta_ble_bed import BleSutaBed

from mqtt_device import MqttDevice
from consts import MqttPayload, SUTA_MANUFACTURER

import logging
from typing import List

# Experimentally determined. Number of times you need to send "raise_head" to get the bed to the top stop.
HEAD_POSITION_MAX = 39
FEET_POSITION_MAX = 20

class MqttSutaBed(MqttDevice):
    '''
    Handle BLE communications and MQTT objects for a SUTA bed frame
    '''
    def __init__(self, bed: BleSutaBed) -> None:
        self.bed: BleSutaBed = bed

    def sanitised_mac(self) -> str:
        '''
        Return my connection address in a form which is suitable where colons aren't
        '''
        return self.bed.device.address.replace(":", "_")

    def get_device_definition(self):
        return {
            # This connection may strictly not be a MAC if you are (for instance) running on
            # MacOS where Bleak isn't allowed to acces the MAC information.
            "name": self.bed.device.name,
            "connections": [("mac", self.bed.device.address)],
            "model": self.bed.device.name,
            "manufacturer": SUTA_MANUFACTURER,
            "suggested_area": "Bedroom",
        }

    def topic_root(self) -> str:
        return f"{SUTA_MANUFACTURER}/{self.sanitised_mac()}"

    def state_topic(self) -> str:
        return f"{self.topic_root()}/state"

    def pairing_button_command_topic(self) -> str:
        return f"{self.topic_root()}/pairing_button/set"

    def head_control_command_topic(self) -> str:
        return f"{self.topic_root()}/head_control/set"

    def raise_head_button_command_topic(self) -> str:
        return f"{self.topic_root()}/raise_head/set"

    def lower_head_button_command_topic(self) -> str:
        return f"{self.topic_root()}/lower_head/set"
    
    async def control_head(self, position: float) -> None:
        """
        Decode the position, which is a percentage value, to a number of moves of the head of the bed.
        As far as I can tell, it is not possible to ask the bed what position it is at,
        so there is no way to know we are doing the right thing.
        """
        target_position = round(HEAD_POSITION_MAX * position/100)

        if target_position == self.head_position:
            return
        elif target_position < self.head_position:
            while target_position < self.head_position:
                await self.bed.lower_head()
                await asyncio.sleep(0.5)
                self.head_position = max(self.head_position - 1, 0)
        elif target_position > self.head_position:
            while target_position > self.head_position:
                await self.bed.raise_head()
                await asyncio.sleep(0.5)
                self.head_position = min(self.head_position + 1, 0)

    def get_unpaired_entities(self, discovery_prefix) -> List[MqttPayload]:
        return [
            MqttPayload(
            topic= f"{discovery_prefix}/button/{self.sanitised_mac()}/pairing_button/config",
            payload={
                "name": f"Pair With Device",
                "device": self.get_device_definition(),
                "unique_id": f"{self.bed.device.address}_pairing_button",
                "icon": "mdi:bed",
                "command_topic": self.pairing_button_command_topic(),
                },
            retain=False
            )
        ]
    
    def get_discovery_entities(self, discovery_prefix: str) -> List[MqttPayload]:
        return [
            MqttPayload(
            topic= f"{discovery_prefix}/button/{self.sanitised_mac()}/raise_head_button/config",
            payload={
                "name": f"Raise head",
                "device": self.get_device_definition(),
                "unique_id": f"{self.bed.device.address}_raise_head_button",
                "icon": "mdi:head",
                "command_topic": self.raise_head_button_command_topic(),
                "availability_topic": self.state_topic(),
                "availability_template": "{{ value_json.availability }}",
                },
            ),

            MqttPayload(
            topic= f"{discovery_prefix}/button/{self.sanitised_mac()}/lower_head_button/config",
            payload={
                "name": f"Lower head",
                "device": self.get_device_definition(),
                "unique_id": f"{self.bed.device.address}_lower_head_button",
                "icon": "mdi:head",
                "command_topic": self.lower_head_button_command_topic(),
                "availability_topic": self.state_topic(),
                "availability_template": "{{ value_json.availability }}",
                },
            ),

            MqttPayload(
            topic= f"{discovery_prefix}/number/{self.sanitised_mac()}/head_control/config",
            payload={
                "name": f"Head",
                "device": self.get_device_definition(),
                "unique_id": f"{self.bed.device.address}_head_control",
                "icon": "mdi:head",
                "min": 0,
                "max": 100,
                "unit_of_measurement": "%",
                "command_topic": self.head_control_command_topic(),
                "state_topic": self.state_topic(),
                "value_template": "{{ value_json.head_position }}",
                "availability_topic": self.state_topic(),
                "availability_template": "{{ value_json.availability }}",
                },
            ),
        ]
    
    async def handle_command(self, bridge, topic: str, message: str) -> None:
        if topic == self.pairing_button_command_topic():
            await bridge.remove_unpaired_device(self.bed.device.address)
            await bridge.add_tracked_device(self.bed.device.address, self)
        elif topic == self.raise_head_button_command_topic():
            await self.bed.raise_head()
            self.head_position += 1
        elif topic == self.lower_head_button_command_topic():
            await self.bed.lower_head()
            self.head_position -= 1
        elif topic == self.head_control_command_topic():
            await self.control_head(float(message))
        else:
            logging.error(f"Unknown command: {topic}")
        pass

    async def get_update(self, online: bool) -> MqttPayload:
        state = {
            "availability": "online" if online else "offline",
            # Convert the positions back to percentage
            "head_position": self.head_position * 100 // HEAD_POSITION_MAX,
            "feet_position": self.feet_position * 100 // FEET_POSITION_MAX,
        }
        update_payload: MqttPayload = MqttPayload(
            topic=self.state_topic(),
            payload=state
        )
        return update_payload
