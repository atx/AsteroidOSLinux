
import argparse
import collections
import datetime
import functools
import itertools
import random
import struct
import time
import xml
from asteroid import bleee
from gi.repository import GLib


def ensure_connected(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        # Note that this does not really strongly guarantee anything as the
        # device can disconnect at any time
        self.connect()
        ret = fn(self, *args, **kwargs)
        # Do we want to schedule a disconnect? Or is BLE low power enough?
        return ret
    return wrapper


class WeatherPredictions:

    Prediction = collections.namedtuple("Prediction", ["id_", "min_", "max_"])

    MAX_LEN = 5

    def __init__(self, city_name):
        self.city_name = city_name
        self.values = []

    def append_prediction(self, id_, min_, max_):
        if len(self.values) >= WeatherPredictions.MAX_LEN:
            raise ValueError("Maximum length exceeded")
        self.values.append(WeatherPredictions.Prediction(
                                    id_=id_, min_=min_, max_=max_))

    @classmethod
    def from_owm(class_, owmforecast):
        # We will get None if the name is no
        loc = owmforecast.get_location()
        name = loc.get_name()
        if not name:
            name = "%.3f %.3f" % (loc.get_lat(), loc.get_lon())
        ret = class_(name)
        for x in range(WeatherPredictions.MAX_LEN):
            w = owmforecast.get(x)
            ret.append_prediction(w.get_weather_code(),
                                  w.get_temperature()["min"],
                                  w.get_temperature()["max"])
        return ret


class Asteroid:

    UUID_BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
    UUID_TIME = "00005001-0000-0000-0000-00a57e401d05"
    UUID_SCREENSHOT_REQ = "00006001-0000-0000-0000-00a57e401d05"
    UUID_SCREENSHOT_RESP = "00006002-0000-0000-0000-00a57e401d05"
    UUID_NOTIF_UPD = "00009001-0000-0000-0000-00a57e401d05"
    UUID_WEATHER_CITY = "00008001-0000-0000-0000-00a57e401d05"
    UUID_WEATHER_IDS = "00008002-0000-0000-0000-00a57e401d05"
    UUID_WEATHER_MINT = "00008003-0000-0000-0000-00a57e401d05"
    UUID_WEATHER_MAXT = "00008004-0000-0000-0000-00a57e401d05"
    UUID_MEDIA_TITLE = "00007001-0000-0000-0000-00a57e401d05"
    UUID_MEDIA_ALBUM = "00007002-0000-0000-0000-00a57e401d05"
    UUID_MEDIA_ARTIST = "00007003-0000-0000-0000-00a57e401d05"
    UUID_MEDIA_PLAY = "00007004-0000-0000-0000-00a57e401d05"
    UUID_MEDIA_COMM = "00007005-0000-0000-0000-00a57e401d05"

    MEDIA_COMMAND_PREVIOUS = 0x0
    MEDIA_COMMAND_NEXT = 0x1
    MEDIA_COMMAND_PLAY = 0x2
    MEDIA_COMMAND_PAUSE = 0x3

    def __init__(self, address):
        self.ble = bleee.BLE()
        self.address = address
        self.dev = self.ble.device_by_address(self.address)
        self.disconnect_timeout = None
        self._disconnect_id = None

    def connect(self):
        # We also want to wait until services are resolved
        while not self.dev.connected or not self.dev.services_resolved:
            if not self.dev.connected:
                try:
                    # Problematically, dbus calls block the entire event loop
                    # TODO: Fix this
                    self.dev.connect()
                except GLib.GError:
                    # Just ignore everything for now
                    pass
            else:
                time.sleep(0.1)

    @ensure_connected
    def battery_level(self):
        return self.dev.char_by_uuid(Asteroid.UUID_BATTERY).read()[0]

    @ensure_connected
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

    @ensure_connected
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

    @ensure_connected
    def notify(self, summary, body=None, id_=None, package_name=None,
               app_name=None, app_icon=None):
        if id_ is None:
            id_ = random.randint(0, 2 ** 31)
        id_ = str(id_)
        xinsert = xml.etree.ElementTree.Element("insert")
        for vl, xn in ((summary, "su"),
                       (body, "bo"),
                       (id_, "id"),
                       (package_name, "pn"),
                       (app_name, "an"),
                       (app_icon, "ai")):
            if vl is not None:
                xel = xml.etree.ElementTree.SubElement(xinsert, xn)
                xel.text = vl
        data = xml.etree.ElementTree.tostring(xinsert)
        self.dev.char_by_uuid(Asteroid.UUID_NOTIF_UPD).write(data)
        return id_

    @ensure_connected
    def update_weather(self, predictions):
        # Set city name
        self.dev.char_by_uuid(Asteroid.UUID_WEATHER_CITY).write(
            predictions.city_name.encode())
        self.dev.char_by_uuid(Asteroid.UUID_WEATHER_IDS).write(
            struct.pack(">5H", *[round(p.id_) for p in predictions.values]))
        self.dev.char_by_uuid(Asteroid.UUID_WEATHER_MINT).write(
            struct.pack(">5H", *[round(p.min_) for p in predictions.values]))
        self.dev.char_by_uuid(Asteroid.UUID_WEATHER_MAXT).write(
            struct.pack(">5H", *[round(p.max_) for p in predictions.values]))

    def update_media(self, title, album, artist, playing):
        self.dev.char_by_uuid(Asteroid.UUID_MEDIA_TITLE).write(title.encode())
        self.dev.char_by_uuid(Asteroid.UUID_MEDIA_ALBUM).write(album.encode())
        self.dev.char_by_uuid(Asteroid.UUID_MEDIA_ARTIST).write(artist.encode())
        self.dev.char_by_uuid(Asteroid.UUID_MEDIA_PLAY).write(
            b"\x01" if playing else b"\x00")

    def register_media_listener(self, fn):
        # TODO: A way to unregister
        ccomm = self.dev.char_by_uuid(Asteroid.UUID_MEDIA_COMM)
        def cb(name, vals, lst):
            if not "Value" in vals:
                return
            fn(vals["Value"][0])
        ccomm.properties_changed.connect(cb)
        ccomm.start_notify()


class DBusEavesdropper:

    def __init__(self, bus, interface, member, callback):
        self.bus = bus
        self.interface = interface
        self.member = member
        self.callback = callback
        self._dbus_ctl = self.bus.get("org.freedesktop.DBus")
        # TODO: Escaping
        # TODO: We probably want to unregister when destroyed?
        self._match_id = self._dbus_ctl.AddMatch(
                            "interface=%s,member=%s,eavesdrop=true" %
                            (interface, member))
        self.bus.con.add_filter(self._filter_func)

    def _filter_func(self, con, msg, bl):
        if msg.get_interface() == self.interface and \
                msg.get_member() == self.member:
            self.callback(msg)
