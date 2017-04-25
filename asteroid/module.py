
import time
import logging
import queue
import threading
import pydbus as dbus
from asteroid import DBusEavesdropper
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

    # TODO: We probably want to have this a bit more sophisticated solution in
    # the future
    registry = dict()

    def __init__(self, name, bases, dict_):
        self.logger = logging.getLogger(name)
        if bases:
            MetaModule.registry[self.name] = self


class Module(metaclass=MetaModule):

    defconfig = dict()

    def __init__(self, asteroid, config):
        self.asteroid = asteroid
        self.config = merge_dicts(self.defconfig, config)
        self.asteroid.dev.properties_changed.connect(self._properties_changed)

    def _properties_changed(self, name, changed, lst):
        pass


class TimeSyncModule(Module):

    name = "timesync"

    def __init__(self, asteroid, config):
        super(TimeSyncModule, self).__init__(asteroid, config)
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

    name = "reconnect"
    defconfig = {"timeout_base": 5,
                 "timeout_max": 300,
                 "timeout_reset": 120}

    def __init__(self, asteroid, config):
        super(ReconnectModule, self).__init__(asteroid, config)
        self._last_connected = 0.0
        self._timeout = 0
        self._condvar = threading.Condition()
        self._thread = threading.Thread(target=self._reconnect_fn)
        self._thread.daemon = True
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

    name = "notify"

    def __init__(self, asteroid, config):
        super(NotifyModule, self).__init__(asteroid, config)
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
