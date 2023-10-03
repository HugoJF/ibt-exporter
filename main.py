# -*- coding: utf-8 -*-

import argparse
import asyncio
import logging
from threading import Thread

from bleak import BleakClient, BleakScanner, BLEDevice, AdvertisementData
from bleak.backends.characteristic import BleakGATTCharacteristic
from flask import Flask
from prometheus_client import generate_latest, CollectorRegistry, Gauge
from prometheus_client.exposition import CONTENT_TYPE_LATEST

app = Flask(__name__)

# Create a Prometheus metric
registry = CollectorRegistry()
temperature = Gauge('ibt_temperature_celsius', 'Example metric for Prometheus', registry=registry, labelnames=['name'])
last_received = Gauge('ibt_last_received_timestamp_seconds', 'Example metric for Prometheus', registry=registry)


@app.route('/metrics')
def metrics():
    # Generate the Prometheus-compatible payload
    return generate_latest(registry), 200, {'Content-Type': CONTENT_TYPE_LATEST}


logger = logging.getLogger(__name__)

data_characteristic = "0000fff4-0000-1000-8000-00805f9b34fb"
settings_characteristic = "0000fff5-0000-1000-8000-00805f9b34fb"


def bytes_to_temperature(data: bytearray):
    raw = int.from_bytes(data, byteorder='little')

    if raw == 0xffff:
        return 0

    return raw / 10


def data_notify_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    logger.info("%s: %r", characteristic.description, data)

    temp1 = bytes_to_temperature(data[0:2])
    temp2 = bytes_to_temperature(data[2:4])

    # Set the value of the metric
    temperature.labels(name=args.probe1_name).set(temp1)
    temperature.labels(name=args.probe2_name).set(temp2)
    last_received.set_to_current_time()

    logger.info("t1: %f - t2: %f", temp1, temp2)


def simple_callback(device: BLEDevice, advertisement_data: AdvertisementData):
    logger.info("%s: %r", device.address, advertisement_data)


async def scan_devices():
    print("scanning devices for 5 seconds, please wait...")

    devices = await BleakScanner.discover(
        return_adv=True
    )

    for d, a in devices.values():
        print(d)
        print(a)
        print("-" * len(str(d)))


def web():
    app.run(host='0.0.0.0', port=8080)


async def main(args: argparse.Namespace):
    while True:
        try:
            logger.info("starting scan...")

            await scan_devices()

            device = await BleakScanner.find_device_by_address(
                args.address
            )
            if device is None:
                raise Exception("could not find device with address '%s'", args.address)

            logger.info("connecting to device...")

            async with BleakClient(device) as client:
                logger.info("Connected")

                # print all services
                for service in client.services:
                    print('service', service)
                    # print characteristics
                    for char in service.characteristics:
                        print('> char', char)

                use_celsius = bytearray([0x02, 0x00, 0x00, 0x00, 0x00, 0x00])
                enable_realtime = bytearray([0x0B, 0x01, 0x00, 0x00, 0x00, 0x00])

                await client.write_gatt_char(settings_characteristic, use_celsius)
                await client.write_gatt_char(settings_characteristic, enable_realtime)

                logger.info("Starting data notify")
                await client.start_notify(data_characteristic, data_notify_handler)
                try:
                    while True:
                        await asyncio.sleep(5)  # Add a small sleep to avoid CPU usage
                        if not client.is_connected:
                            raise Exception("Disconnected")
                except KeyboardInterrupt:
                    pass
                await client.stop_notify(data_characteristic)
        except Exception as e:
            logger.exception("Exception in main loop")
            logger.error(e)
            logger.info("Retrying in 5 seconds...")
            await asyncio.sleep(5.0)


if __name__ == "__main__":
    global args

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--address",
        metavar="<address>",
        help="the address of the bluetooth device to connect to",
    )
    parser.add_argument(
        "--probe1-name",
        metavar="<name>",
        help="the name of the first probe",
    )
    parser.add_argument(
        "--probe2-name",
        metavar="<name>",
        help="the name of the second probe",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="sets the log level to debug",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
    )
    t2 = Thread(target=web)
    t2.start()

    asyncio.run(main(args))
    t2.join()
