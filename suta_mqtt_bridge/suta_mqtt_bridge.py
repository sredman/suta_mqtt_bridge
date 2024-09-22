"""Main module."""

from suta_ble_bed import BleSutaBed
from mqtt_suta_bed import MqttSutaBed
from mqtt_bridge import MqttBridge
from consts import MqttPayload, SUTA_MANUFACTURER

from suta_ble_bed.suta_ble_bed_controller import SutaBleBedController

import asyncio
from bleak import BleakError
import logging

logger = logging.getLogger(__name__)

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
        self.bluetooth_wait_interval_seconds = 10

    async def start(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.mqtt_bridge.start())
            tg.create_task(self.start_device_scanning())

    async def start_device_scanning(self) -> None:
        async with SutaBleBedController() as controller:
            async for bed in controller.devices():
                logger.info(f"Discovered {bed.device}")
                wrapped_bed = MqttSutaBed(bed)

                if bed.device.address in self.mqtt_bridge.known_devices:
                    # This is a device with which we are paired, either due to the pairing having been broken
                    # or due to another device on the same MQTT network having paired.
                    # Presumably, the user wants us to connect to this device as well.
                    # (To prevent this from hapening, delete the device in Home Assistant or manually remove the MQTT topic.)
                    await controller.connect(wrapped_bed.bed)
                    await self.mqtt_bridge.add_tracked_device(key = bed.device.address, device = wrapped_bed)
                elif not bed.device.address in self.mqtt_bridge.unpaired_devices:
                    # This is a device we have not seen before. Add it as unpaired.
                    await self.mqtt_bridge.add_unpaired_device(key = bed.device.address, device = wrapped_bed)

                # Yield the thread to avoid starving anyone else, since the BLE discovery can be noisy
                await asyncio.sleep(0)

        while True:
            discovered_devices = [device for device in await suta_scanner.discover(mac = None, adapter = self.adapter, wait = self.bluetooth_wait_interval_seconds)]
            discovered_device_addresses = [device.address for device in discovered_devices]
            newly_discovered_devices = [device for device in discovered_devices if device.address not in self.mqtt_bridge.tracked_devices and device not in self.mqtt_bridge.unpaired_devices]
            for device in newly_discovered_devices:
                pass

            missing_devices = [] # Paired devices which we could not find
            for addr in self.mqtt_bridge.tracked_devices:
                device = self.mqtt_bridge.tracked_devices[addr]
                if addr not in discovered_device_addresses:
                    # We are supposed to have been controlling this device but it is no longer in range. Mark it as such.
                    missing_devices.append(addr)
                else:
                    try:
                        await self.mqtt_bridge.enqueue_update(device, online=True)
                    except BleakError as be:
                        if addr in self.tracked_mugs:
                            missing_devices.append(addr)
                        logging.warning(f"Error while communicating with device: {be}")

            for addr in missing_devices:
                await self.mqtt_bridge.remove_tracked_device(addr)

            gone_unpaired_device_addresses = set()
            for unpaired_address in self.mqtt_bridge.unpaired_devices:
                # Clean up any unpaired devices we no longer see
                if not unpaired_address in discovered_device_addresses:
                    gone_unpaired_device_addresses.add(unpaired_address)

            for gone_device_address in gone_unpaired_device_addresses:
                await self.mqtt_bridge.remove_unpaired_device(gone_device_address)

            await asyncio.sleep(self.update_interval)