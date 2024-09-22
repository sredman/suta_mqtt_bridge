#!/usr/bin/env python3
#
# Filename: mqtt_bridge.py
#
# Author: Simon Redman <simon@ergotech.com>
# File Created: 03.21.2023
# Description: Mqtt handler for arbitary devices
#

from consts import MqttPayload
from mqtt_device import MqttDevice

import asyncio
from aiomqtt import Client, MqttError
import json
import logging
from typing import Dict, Set, List

class MqttBridge:
    def __init__(
        self,
        mqtt_broker,
        mqtt_broker_port,
        mqtt_username,
        mqtt_password,
        discovery_prefix,
        command_prefix,
        manufacturer_strings,
        **kwargs
        ):
        """
        Create the entity which will handle MQTT communication.

        @param mqtt_broker: DNS name for the MQTT broker
        @param mqtt_broker_port: Port on which the MQTT broker is listening
        @param mqtt_username: Username with which to authenticate to the MQTT broker
        @param mqtt_password: Password with which to authenticate to the MQTT broker
        @param discovery_prefix: Prefix expected to discover existing devices
        @param command_prefix: Prefix expected when receiving commands
        @param manufacturer_strings: Strings to use to identify devices controlled by this bridge
        """
        self.mqtt_broker = mqtt_broker
        self.mqtt_broker_port = mqtt_broker_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.discovery_prefix = discovery_prefix
        self.command_prefix = command_prefix
        self.manufacturer_strings = manufacturer_strings

        # Put all required parameters above this line and all optional fields below this line
        self.validate_parameters()

        # Devices to which we are connected and controlling
        self.tracked_devices: Dict[str, MqttDevice] = {}
        self.incoming_tracked_devices: Dict[str, MqttDevice] = {}
        self.outgoing_tracked_devices: Set[str] = set()
        # Devices which we can see but with which we are not supposed to talk
        self.unpaired_devices: Dict[str, MqttDevice] = {}
        self.incoming_unpaired_devices: Dict[str, MqttDevice] = {}
        self.outgoing_unpaired_devices: Set[str] = set()

        self.new_device_event = asyncio.Event()
        self.done_processing_new_devices = asyncio.Event()
        self.done_processing_new_devices.set()

        self.outgoing_messages = asyncio.Queue()

        self.retry_interval_secs = 1

        self.logger = logging.getLogger(__name__)

        # Devices which we know about from seeing thier MQTT advertisements,
        # but with which we may or may not be connected.
        self.known_devices: Set[str] = set()
        self.done_processing_existing_known_devices_event = asyncio.Event()

    def validate_parameters(self):
        unsupplied_params = [var for var in vars(self) if getattr(self, var) is None]

        if len(unsupplied_params) > 0:
            raise ExceptionGroup(
                "One or more parameters was not provided",
                [ValueError(param) for param in unsupplied_params])

    async def start(self):
        while True:
            try:
                async with Client(
                    hostname=self.mqtt_broker,
                    port=self.mqtt_broker_port,
                    username=self.mqtt_username,
                    password=self.mqtt_password,
                    ) as client:
                    try:
                        async with asyncio.TaskGroup() as tg:
                            tg.create_task(self.start_mqtt_listener(client))
                            tg.create_task(self.start_device_listener(client))
                            tg.create_task(self.start_outgoing_message_handler(client))
                    except:
                        # We are closing down. Send out a notice that the devices we control are offline.
                        for mqtt_device in self.tracked_devices.values():
                            await self._remove_tracked_device(client, mqtt_device)
                        for mqtt_device in self.unpaired_devices.values():
                            await self._remove_unpaired_device(client, mqtt_device)
                        raise
            except MqttError as err:
                self.logger.warning(f"MQTT connection failed with {err}")
                await asyncio.sleep(self.retry_interval_secs)

    async def start_mqtt_listener(self, mqtt: Client):
        await mqtt.subscribe(f"{self.discovery_prefix}/#") # Listen for knowledge of device we cannot see
        async for message in mqtt.messages:
            topic = message.topic.value
            if topic.startswith(f"{self.discovery_prefix}"):
                '''
                Look for MQTT messages indicating devices which have been discovered in the past,
                which we should be on the lookout for.
                These devices may be from other bridges running on the same MQTT server,
                so we _cannot_ expect that they are paired.
                '''
                if message.payload and message.retain != 0:
                    data = json.loads(message.payload)
                    if data and "device" in data:
                        device = data["device"]
                        if "connections" in device and "manufacturer" in device:
                            if device["manufacturer"] in self.manufacturer_strings:
                                connections = device["connections"]
                                self.known_devices.add(connections[0][1])
                elif message.payload is None:
                    # This is a device which is being deleted
                    # TODO: Handle this case, so that we don't immediately re-discover mugs which the user has tried to delete.
                    pass
                else:
                    # Non-retained messages indicate a device which is not "known", maybe in pairing state at best.
                    pass
            if len(mqtt.messages) == 0:
                self.done_processing_existing_known_devices_event.set()

            if topic.startswith(self.command_prefix) and topic.endswith("set"):
                '''
                Look for messages indicating a command from the user.
                TODO: Make this section gracefully accept devices which are handled by another MQTT instance
                '''
                # Get the device to which this message belongs
                # There is certainly a better way to do this but I am lazy
                matching_devices = [mqtt_device for mqtt_device in self.tracked_devices.values() if topic.startswith(mqtt_device.topic_root())]
                matching_devices = matching_devices + [mqtt_device for mqtt_device in self.unpaired_devices.values() if topic.startswith(mqtt_device.topic_root())]
                if len(matching_devices) == 0:
                    logging.error(f"No devices matched {topic}. This is a bug.")
                elif len(matching_devices) > 1:
                    logging.error(f"More than one device matched {topic}. This is a bug.")
                else:
                    mqtt_device = matching_devices[0]

                    try:
                        await mqtt_device.handle_command(self, topic, message.payload.decode())
                    except Exception as e:
                        # Something went wrong with this device, did it become unavailable?
                        logging.warn(f"Error occurred handling {topic}, {e}")
    
    async def start_device_listener(self, mqtt) -> None:
        """
        Handle events indicating a new device has been added
        """
        while True:
            await self.new_device_event.wait()
            self.new_device_event.clear()
            self.done_processing_new_devices.clear()

            for key in self.incoming_unpaired_devices:
                device = self.incoming_unpaired_devices[key]
                self.unpaired_devices[key] = device
                await self.subscribe_mqtt_topic(mqtt, device)
                await self.send_unpaired_entity_discovery(mqtt, device)

            self.incoming_unpaired_devices = {}

            for key in self.outgoing_unpaired_devices:
                device = self.unpaired_devices[key]
                await self.unsubscribe_mqtt_topic(mqtt, device)
                await self._remove_unpaired_device(mqtt, device)
                del self.unpaired_devices[key]

            self.outgoing_unpaired_devices = set()

            for key in self.incoming_tracked_devices:
                device = self.incoming_tracked_devices[key]
                self.tracked_devices[key] = device
                await self.subscribe_mqtt_topic(mqtt, device)
                await self.send_entity_discovery(mqtt, device)
                await self.enqueue_update(device, online=True)

            self.incoming_tracked_devices = {}

            for key in self.outgoing_tracked_devices:
                device = self.tracked_devices[key]
                await self.unsubscribe_mqtt_topic(mqtt, device)
                await self._remove_unpaired_device(mqtt, device)
                del self.tracked_devices[key]

            self.outgoing_tracked_devices = set()

            self.done_processing_new_devices.set()

    async def start_outgoing_message_handler(self, mqtt) -> None:
        while True:
            message: MqttPayload = await self.outgoing_messages.get()
            await mqtt.publish(message.topic, json.dumps(message.payload), retain=message.retain)

    async def add_tracked_device(self, key: str, device: MqttDevice) -> None:
        await self.done_processing_new_devices.wait()
        self.incoming_tracked_devices[key] = device
        self.new_device_event.set()

    async def remove_tracked_device(self, key:str) -> None:
        await self.done_processing_new_devices.wait()
        device = self.tracked_devices[key]
        await self.enqueue_update(device, online=False)
        self.outgoing_tracked_devices.add(key)
        self.new_device_event.set()

    async def add_unpaired_device(self, key: str, device: MqttDevice) -> None:
        await self.done_processing_new_devices.wait()
        self.incoming_unpaired_devices[key] = device
        self.new_device_event.set()

    async def remove_unpaired_device(self, key:str) -> None:
        await self.done_processing_new_devices.wait()
        self.outgoing_unpaired_devices.add(key)
        self.new_device_event.set()

    async def enqueue_update(self, device: MqttDevice, online: bool) -> None:
        """
        Request an update message be sent
        """
        state = await device.get_update(online=online)
        await self.outgoing_messages.put(state)

    async def _remove_tracked_device(self, mqtt: Client, device: MqttDevice) -> None:
        message: MqttPayload = await device.get_update(online=False)
        await mqtt.publish(message.topic, json.dumps(message.payload), retain=message.retain)

    async def _remove_unpaired_device(self, mqtt: Client, device: MqttDevice) -> None:
        entities: List[MqttPayload] = device.get_unpaired_entities(discovery_prefix=self.discovery_prefix)
        for entity in entities:
            await mqtt.publish(entity.topic, None, retain=False)

    async def subscribe_mqtt_topic(self, mqtt: Client, device: MqttDevice):
        '''
        Subscribe to the update topics for the given device.
        '''
        await mqtt.subscribe(f"{device.topic_root()}/+/set")

    async def unsubscribe_mqtt_topic(self, mqtt: Client, device: MqttDevice):
        '''
        Unsubscribe from the update topics for the given device.
        '''
        await mqtt.unsubscribe(f"{device.topic_root()}/+/set")

    async def send_unpaired_entity_discovery(self, mqtt: Client, device: MqttDevice):
        '''
        Broadcast this device in unpaired mode
        '''
        entities: List[MqttPayload] = device.get_unpaired_entities(discovery_prefix=self.discovery_prefix)
        for entity in entities:
            await mqtt.publish(entity.topic, json.dumps(entity.payload), retain=False)

    async def send_entity_discovery(self, mqtt: Client, device: MqttDevice):
        '''
        Broadcast this device in normal, ready-to-use mode
        '''
        entities: List[MqttPayload] = device.get_discovery_entities(discovery_prefix=self.discovery_prefix)
        for entity in entities:
            await mqtt.publish(entity.topic, json.dumps(entity.payload), retain=entity.retain)
