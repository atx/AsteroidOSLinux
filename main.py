#! /usr/bin/env python3

import argparse
import datetime
import itertools
import time
from bluetooth import ble

class Asteroid:

    UUID_BATTERY = "0000180f-0000-1000-8000-00805f9b34fb"
    UUID_TIME = "00005001-0000-0000-0000-00a57e401d05"

    def __init__(self, address):
        self.dev = ble.GATTRequester(address)
        # Not waiting here leads to segfault on characteristics enumeration...
        # TODO: Fix pybluez/gattlib/whatever
        while not self.dev.is_connected():
            time.sleep(0.2)
        time.sleep(1)
        chars = itertools.groupby(self.dev.discover_characteristics(),
                                       lambda x: x["uuid"])
        self.characteristics = {k: list(v)[0] for k, v in chars}
        self.handle_battery = self.characteristics[Asteroid.UUID_BATTERY]
        self.handle_time = self.characteristics[Asteroid.UUID_TIME]

    def battery_level(self):
        return int(self.dev.read_by_handle(self.handle_battery["value_handle"])[0])

    def update_time(self, to=None):
        if to is None:
            to = datetime.datetime.now()
        data = [
            to.year - 1900,
            to.month - 1,
            to.day,
            to.hour,
            to.minute,
            to.second
        ]
        self.dev.write_by_handle(asteroid.handle_time["value_handle"], bytes(data))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AsteroidOSLinux")
    parser.add_argument(
        "-a", "--address",
        required=True,
        help="Bluetooth address of the device"
    )

    args = parser.parse_args()

    asteroid = Asteroid(args.address)

    import IPython
    IPython.embed()
