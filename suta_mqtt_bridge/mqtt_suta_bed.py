#!/usr/bin/env python3
#
# Filename: mqtt_suta_bed.py
#
# Author: Simon Redman <simon@ergotech.com>
# File Created: 03.21.2023
# Description: Handle BLE communications and MQTT objects for a SUTA bed frame
#

from suta_ble_bed import BleSutaBed

from mqtt_device import MqttDevice
from consts import MqttPayload, SUTA_MANUFACTURER

import logging
from typing import List

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

    def raise_head_button_command_topic(self) -> str:
        return f"{self.topic_root()}/raise_head/set"
    
    def get_unpaired_entities(self, discovery_prefix) -> List[MqttPayload]:
        return [
            MqttPayload(
            topic= f"{discovery_prefix}/button/{self.sanitised_mac()}/pairing_button/config",
            payload={
                "name": f"Pair With Device",
                "device": self.get_device_definition(),
                "unique_id": f"{self.bed.device.address}_pairing_button",
                "icon": "mdi:coffee-off-outline",
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
                "icon": "mdi:coffee-off-outline",
                "command_topic": self.raise_head_button_command_topic(),
                "availability_topic": self.state_topic(),
                "availability_template": "{{ value_json.availability }}",
                },
            )
        ]
    
    async def handle_command(self, bridge, topic: str, message: str) -> None:
        if topic == self.pairing_button_command_topic():
            await bridge.remove_unpaired_device(self.bed.device.address)
            await bridge.add_tracked_device(self.bed.device.address, self)
        else:
            logging.error(f"Unknown command: {topic}")
        pass

    async def get_update(self, online: bool) -> MqttPayload:
        state = {
            "availability": "online" if online else "offline",
        }
        update_payload: MqttPayload = MqttPayload(
            topic=self.state_topic(),
            payload=state
        )
        return update_payload
