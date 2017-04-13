#! /usr/bin/env python3

import argparse
import datetime
import itertools
import struct
import time
import bleee
from gi.repository import GLib

class Asteroid:

    UUID_BATTERY = "0000180f-0000-1000-8000-00805f9b34fb"
    UUID_TIME = "00005001-0000-0000-0000-00a57e401d05"
    UUID_SCREENSHOT_REQ = "00006001-0000-0000-0000-00a57e401d05"
    UUID_SCREENSHOT_RESP = "00006002-0000-0000-0000-00a57e401d05"

    def __init__(self, address):
        self.ble = bleee.BLE()
        self.address = address
        self.dev = self.ble.device_by_address(self.address)
        # TODO: Manage this more properly
        self.dev.connect()

    def battery_level(self):
        return int(self.dev.char_by_uuid(Asteroid.UUID_BATTERY).read())

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
        self.dev.char_by_uuid(Asteroid.UUID_TIME).write(data)

    def screenshot(self):
        # TODO: This disconnects after a few callbacks, fix
        crsp = self.dev.char_by_uuid(Asteroid.UUID_SCREENSHOT_RESP)
        loop = GLib.MainLoop()
        data_rem = None
        def cb(*args):
            print(args)
            #loop.quit()
        crsp.start_notify()
        crsp.properties_changed.connect(cb)
        self.dev.char_by_uuid(Asteroid.UUID_SCREENSHOT_REQ).write(b"\x00")
        loop.run()

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
