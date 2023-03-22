#!/usr/bin/env python3
#
# Filename: cli.py
#
# Author: Simon Redman <simon@ergotech.com>
# File Created: 01.03.2023
# Last Modified: Sat 25 Feb 2023 08:38:58 PM EST
# Description: Integrate your SUTA bed with your MQTT server
#

import argparse
import asyncio
import sys
import yaml

from suta_mqtt_bridge import SutaMqttBridge

import time
time.sleep(5)

def main():
    parser = argparse.ArgumentParser(
        prog="SutaMqttBridge",
        description="Integrate your SUTA bed with your MQTT server")
    
    parser.add_argument("-c", "--config-file",
        help="Path to a YAML file from which to read options. If any options are specified in this file and on the command line, the command line option will take prescidence.")

    parser.add_argument("-b", "--mqtt-broker",
        help="Target MQTT broker, like test.mosquitto.org.")

    parser.add_argument("-P", "--mqtt-broker-port", type=int, default=1883,
        help="Target MQTT broker port, like 1883.")
    
    parser.add_argument("-u", "--mqtt-username",
        help="Username to authenticate to the MQTT broker.")

    parser.add_argument("-p", "--mqtt-password",
        help="Password to authenticate to the MQTT broker.")

    parser.add_argument("-i", "--update-interval", type=int, default=30,
        help="Frequency at which to send out update messages, in seconds.")

    parser.add_argument("--discovery-prefix", default="homeassistant",
        help="MQTT discovery prefix.")

    parser.add_argument("--adapter", required=False, type=str, default=None,
        help="Bluetooth adapter to select, like \"hci0\"")

    args = parser.parse_args()
    config = {}

    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)

    for arg in vars(args):
        val = getattr(args, arg)
        if val is not None:
            config[arg] = val
        if arg not in config:
            config[arg] = val

    del config["config_file"]

    controller = SutaMqttBridge(**config)
    asyncio.run(controller.start()) # Should never return


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
