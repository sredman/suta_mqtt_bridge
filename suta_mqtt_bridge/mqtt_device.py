#!/usr/bin/env python3
#
# Filename: mqtt_device.py
#
# Author: Simon Redman <simon@ergotech.com>
# File Created: 03.21.2023
# Description: Abstract device which is the parent of all MQTT devices handle-able by this bridge
#

from consts import MqttPayload

from abc import ABC, abstractmethod

from typing import List

class MqttDevice(ABC):
    """
    Abstract device which is the parent of all MQTT devices handle-able by the MqttBridge
    """

    @abstractmethod
    def topic_root(self) -> str:
        pass

    @abstractmethod
    def get_unpaired_entities(self, discovery_prefix: str) -> List[MqttPayload]:
        """
        Return entities which represent an unpaired object, such as a pairing button
        """
        pass

    @abstractmethod
    def get_discovery_entities(self, discovery_prefix: str) -> List[MqttPayload]:
        """
        Return entities which represent an ready-to-use object
        """
        pass

    @abstractmethod
    async def handle_command(self, bridge, topic: str, message: str) -> None:
        """
        Handle the command specified in the topic and message

        @param bridge: The MqttBridge controlling this device
        @param topic: The MQTT topic which was triggered
        @param message: The MQTT message sent with this payload
        """
        pass