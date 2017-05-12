
import time
import logging
import queue
import threading
import mpd
import pyowm
import pydbus as dbus
from asteroid import Asteroid, DBusEavesdropper, WeatherPredictions
from gi.repository import GLib


def merge_dicts(first, second):
    """ Recursively deep merges two dictionaries """
    ret = first.copy()
    for k, v in second.items():
        if isinstance(v, dict) and k in first and isinstance(first[k], dict):
            ret[k] = merge_dicts(first[k], v)
        else:
            ret[k] = v
    return ret


class MetaModule(type):

    def __init__(self, name, bases, dict_):
        self.logger = logging.getLogger(name)


class Module(metaclass=MetaModule):

    defconfig = dict()

    def __init__(self, **kwargs):
        self.config = merge_dicts(self.defconfig, kwargs)

    def register(self, app):
        self.app = app
        self.asteroid = app.asteroid
        self.asteroid.dev.properties_changed.connect(self._properties_changed)

    def _properties_changed(self, name, changed, lst):
        pass


class TimeSyncModule(Module):

    def register(self, app):
        super(TimeSyncModule, self).register(app)
        # We want to do this on startup, but as the dbus-is-blocking issues is
        # not solved yet, be careful
        if self.asteroid.dev.connected:
            self._update_time()

    def _update_time(self):
        self.asteroid.update_time()
        self.logger.info("Time synchronized")

    def _properties_changed(self, name, changed, lst):
        if changed.get("Connected", False):
            self._update_time()


class ReconnectModule(Module):

    defconfig = {"timeout_base": 5,
                 "timeout_max": 300,
                 "timeout_reset": 120}

    def __init__(self, **kwargs):
        super(ReconnectModule, self).__init__(**kwargs)
        self._last_connected = 0.0
        self._timeout = 0
        self._condvar = threading.Condition()
        self._thread = threading.Thread(target=self._reconnect_fn)
        self._thread.daemon = True

    def register(self, app):
        super(ReconnectModule, self).register(app)
        self._thread.start()

    def _reconnect_fn(self):
        while True:
            self._condvar.acquire()
            while self.asteroid.dev.connected:
                self._condvar.wait(10)
            self._condvar.release()
            dt = time.time() - self._last_connected
            if dt > self.config["timeout_reset"]:
                self._timeout = 0
            if self._timeout > 0:
                self.logger.info("Reconnecting in %d seconds..." % self._timeout)
                time.sleep(self._timeout)
            else:
                self.logger.info("Reconnecting...")
            self.asteroid.connect()
            self._timeout = min(self._timeout + self.config["timeout_base"],
                                self.config["timeout_max"])
            self.logger.info("Connected!")

    def _properties_changed(self, name, changed, lst):
        if not changed.get("Connected", True):
            self._condvar.acquire()
            self._condvar.notify()
            self._condvar.release()
        elif changed.get("Connected", False):
            self._last_connected = time.time()


class NotifyModule(Module):

    def register(self, app):
        super(NotifyModule, self).register(app)
        self._pending = queue.Queue()
        self._eavesdropper = DBusEavesdropper(
                                    dbus.SessionBus(),
                                    "org.freedesktop.Notifications",
                                    "Notify",
                                    self._on_notification)

    def _notification_send(self):
        try:
            msg = self._pending.get_nowait()
            app_name, id_, app_icon, summary, body, actions, hints, \
                expiration = msg.get_body()
            self.asteroid.notify(summary, body=body,
                                 id_=(id_ if id_ else None),
                                 app_name=app_name, app_icon=app_icon)
            self.logger.info("Sent notification '%s'" % summary)
        except queue.Empty:
            pass
        return bool(self._pending.qsize())

    def _on_notification(self, msg):
        self._pending.put(msg)
        GLib.idle_add(self._notification_send)


class OWMModule(Module):

    defconfig = {"update_interval": 2 * 60 * 60 }

    def __init__(self, **kwargs):
        super(OWMModule, self).__init__(**kwargs)
        self._owm = pyowm.OWM(self.config["api_key"])

    def register(self, app):
        super(OWMModule, self).register(app)
        self._update_weather()
        GLib.timeout_add_seconds(self.config["update_interval"], self._update_weather)

    def _update_weather(self):
        try:
            # TODO: Eventually, autodetecting the location would be nice
            forecast = self._owm.daily_forecast(self.config["location"]).get_forecast()
            preds = WeatherPredictions.from_owm(forecast)
            self.asteroid.update_weather(preds)
            self.logger.info("Weather update sent")
        except Exception as e:
            self.logger.error("Weather update failed with %s" % e)
        return True


class MPDModule(Module):

    defconfig = {
        "host": "127.0.0.1",
        "port": 6600
    }

    def __init__(self, **kwargs):
        super(MPDModule, self).__init__(**kwargs)
        # We actually make two MPD connections, one for watching changes and
        # other for sending commands.
        self._mpd = self._make_mpd()
        self._mpd_watch = self._make_mpd()

    def _make_mpd(self):
        cl = mpd.MPDClient()
        cl.timeout = 10
        cl.connect(self.config["host"], self.config["port"])
        return cl

    def register(self, app):
        super(MPDModule, self).register(app)
        self.asteroid.register_media_listener(self._command_cb)
        self._send_update()
        self._mpd_watch.send_idle()
        GLib.io_add_watch(self._mpd_watch, GLib.IO_IN, self._mpd_cb)

    def _send_update(self):
        song = self._mpd.currentsong()
        status = self._mpd.status()
        self.asteroid.update_media(
            song.get("title", "Unknown"),
            song.get("album", "Unknown"),
            song.get("artist", "Unknown"),
            status["state"] == "play"
        )

    def _mpd_cb(self, src, cond):
        # We disregard the changes and just send everything
        changes = self._mpd_watch.fetch_idle()
        if "player" in changes:
            self._send_update()
        self._mpd_watch.send_idle()
        return True

    def _command_cb(self, cmd):
        if cmd == Asteroid.MEDIA_COMMAND_PREVIOUS:
            self._mpd.previous()
        elif cmd == Asteroid.MEDIA_COMMAND_NEXT:
            self._mpd.next()
        elif cmd == Asteroid.MEDIA_COMMAND_PLAY:
            self._mpd.play()
        elif cmd == Asteroid.MEDIA_COMMAND_PAUSE:
            self._mpd.pause()
        else:
            self.logger.error("Unknown media command code %02x" % cmd)
