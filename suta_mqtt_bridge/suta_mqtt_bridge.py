"""Main module."""

from suta_ble_bed import BleSutaBed
from mqtt_suta_bed import MqttSutaBed
from mqtt_bridge import MqttBridge
from consts import MqttPayload, SUTA_MANUFACTURER

import suta_ble_bed.suta_ble_scanner as suta_scanner

import asyncio

import logging

class SutaMqttBridge:

    def __init__(
        self,
        adapter: str,
        update_interval: int,
        **kwargs
        ):
        """

        @param adapter: Bluetooth adapter to use, like "hci0"
        @param update_interval: Frequency at which to refresh the bed state
        @param kwargs: Arguments to pass to the MqttBridge constructor
        """
        self.mqtt_bridge = MqttBridge(
            command_prefix=SUTA_MANUFACTURER,
            manufacturer_strings=[SUTA_MANUFACTURER],
            **kwargs)
        self.adapter = adapter
        self.update_interval = update_interval

    async def start(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.mqtt_bridge.start())
            tg.create_task(self.start_device_polling())

    async def start_device_polling(self) -> None:
        while True:
            unpaired_devices = [device for device in await suta_scanner.discover(mac = None, adapter = self.adapter, wait = self.update_interval)] # Find mugs in pairing mode
            for unpaired_device in unpaired_devices:
                if unpaired_device.address in self.mqtt_bridge.known_devices:
                    # This is a device with which we are paired, either due to the pairing having been broken
                    # or due to another device on the same MQTT network having paired.
                    # Presumably, the user wants us to connect to this device as well.
                    # (To prevent this from hapening, delete the device in Home Assistant or manually remove the MQTT topic.)
                    async with BleSutaBed(unpaired_device).connection():
                        pass # Connecting the bluetooth is sufficient. The next iteration will handle everything correctly.
                elif not unpaired_device.address in self.mqtt_bridge.unpaired_devices:
                    wrapped_bed = MqttSutaBed(BleSutaBed(unpaired_device))
                    await self.mqtt_bridge.add_unpaired_device(key = unpaired_device.address, device = wrapped_bed)

            missing_mugs = [] # Paired devices which we could not find
            for addr in self.mqtt_bridge.known_devices:
                if addr in self.mqtt_bridge.tracked_devices:
                    if self.mqtt_bridge.tracked_devices[addr].device._client.is_connected:
                        pass # Already connected, nothing to do
                    else:
                        missing_mugs.append(addr)
                else:
                    device = await ember_mug_scanner.find_mug(addr, adapter = self.adapter) # Find paired mugs
                    if device is None:
                        pass # I guess it's not in range. Send an "offline" status update?
                    else:
                        self.tracked_mugs[addr] = MqttEmberMug(EmberMug(device))

            for addr in self.mqtt_bridge.tracked_devices:
                try:
                    device: MqttDevice = self.mqtt_bridge.tracked_devices[addr]
                    mug: EmberMug = wrapped_mug.mug
                    # Using current_temp as a proxy for data being initialized.
                    if mug.data.current_temp == 0:
                        # This intentionally leaves the connection open.
                        # If we do not, we do not get the notices to which we've subscribed.
                        await mug.update_all()
                        await mug.subscribe()
                        await self.subscribe_mqtt_topic(mqtt, wrapped_mug)
                        await self.send_entity_discovery(mqtt, wrapped_mug)

                    changes: List[ember_mug_data.Change] = await mug.update_queued_attributes()

                    # Determine whether we need to send an update to the entity, if one of the top-level configs changed
                    for changed_attr in [change.attr for change in changes]:
                        if changed_attr in consts.NAME_TO_EVENT_ID:
                            attr_code = consts.NAME_TO_EVENT_ID[changed_attr]
                            match attr_code:
                                case ember_mug_consts.PushEvent.LIQUID_STATE_CHANGED:
                                    # We use the LIQUID_STATE to control the "modes" field of the "climate" entity
                                    await self.send_entity_discovery(mqtt, wrapped_mug)

                    await wrapped_mug.send_update(mqtt, online=True)

                except BleakError as be:
                    if addr in self.tracked_mugs:
                        missing_mugs.append(addr)
                    logging.warning(f"Error while communicating with mug: {be}")

            for addr in missing_mugs:
                await self.handle_mug_disconnect(mqtt, addr)

            gone_unpaired_device_addresses = set()
            unpaired_device_addresses = [device.address for device in unpaired_devices]
            for unpaired_address in self.mqtt_bridge.unpaired_devices:
                # Clean up any unpaired devices we no longer see
                if not unpaired_address in unpaired_device_addresses:
                    gone_unpaired_device_addresses.add(unpaired_address)

            for gone_device_address in gone_unpaired_device_addresses:
                wrapped_mug = self.unpaired_mugs[gone_device_address]
                del self.unpaired_mugs[gone_device_address]
                await self.remove_unpaired_mug(mqtt, wrapped_mug)

            await asyncio.sleep(self.update_interval)