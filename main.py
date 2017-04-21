#! /usr/bin/env python3

import argparse
import colorama
import datetime
import pydbus as dbus
import queue
import cmd
import threading
import functools
from gi.repository import GLib
from asteroid import *


# TODO: Eh, probably hook this up with the logging module or something
class Print:

    @staticmethod
    @functools.lru_cache(10)
    def _prefix(prefix, color):
        return colorama.Style.RESET_ALL + "[" + color + prefix + \
            colorama.Style.RESET_ALL + "]"

    @staticmethod
    @functools.wraps(print)
    def info(*args, **kwargs):
        print(Print._prefix("INF", colorama.Fore.LIGHTBLUE_EX), *args,
              **kwargs)

    @staticmethod
    @functools.wraps(print)
    def response(*args, **kwargs):
        print(Print._prefix("RSP", colorama.Fore.LIGHTGREEN_EX), *args,
              **kwargs)


def in_glib(fn):
    def wrapper(*args, **kwargs):
        retq = queue.Queue()

        def glibfn():
            retval = fn(*args, **kwargs)
            retq.put(retval)
            return False

        GLib.timeout_add(0, glibfn)
        # If something kills the event loop at this point, we are fucked
        return retq.get()
    return wrapper


class AsteroidCmd(cmd.Cmd):

    prompt = "[" + colorama.Fore.LIGHTBLUE_EX + "asteroid" + \
        colorama.Style.RESET_ALL + "] "

    def __init__(self, asteroid, loop):
        super(AsteroidCmd, self).__init__()
        self.asteroid = asteroid
        self.asteroid.dev.properties_changed.connect(self._changed_callback)
        self.loop = loop
        self.exiting = False

    def _changed_callback(self, name, changed, lst):
        for k, v in changed.items():
            Print.info("Changed %s = %s" % (k, v))

    @in_glib
    def do_battery(self, line):
        """ Fetches and prints the battery level """
        Print.response("Battery = %d" % self.asteroid.battery_level())

    @in_glib
    def do_update_time(self, line):
        """ Updates time on the watch """
        dt = None
        if line:
            dt = datetime.datetime.strptime(line, "%Y-%m-%d %T")
        self.asteroid.update_time(dt)
        if dt:
            Print.response("Set time to " + dt.isoformat(" "))
        else:
            Print.response("Set time local time")

    def do_ipython(self, line):
        import IPython
        IPython.embed()

    def do_exit(self, line):
        self.loop.quit()
        self.exiting = True

    do_EOF = do_exit

    def postcmd(self, stop, line):
        return self.exiting


class CmdThread(threading.Thread):

    def __init__(self, cmd):
        super(CmdThread, self).__init__()
        self.cmd = cmd

    def run(self):
        self.cmd.cmdloop("")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AsteroidOSLinux")
    parser.add_argument(
        "-a", "--address",
        required=True,
        help="Bluetooth address of the device"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Drop to IPython shell instead of GLib event loop"
    )

    args = parser.parse_args()

    session_bus = dbus.SessionBus()
    asteroid = Asteroid(args.address)

    pending_notifications = queue.Queue()

    def notification_sender():
        try:
            msg = pending_notifications.get_nowait()
            app_name, id_, app_icon, summary, body, actions, hints, \
                expiration = msg.get_body()
            asteroid.notify(summary, body=body, id_=(id_ if id_ else None),
                            app_name=app_name, app_icon=app_icon)
            Print.info("Sent notification '%s'" % summary)
        except queue.Empty:
            pass
        return bool(pending_notifications.qsize())

    def on_notification(msg):
        # Note: Not sure which thread context is this getting executed in,
        # but the event loop _does not_ have to be running for this to be
        # called. This is why the Queue is needed.
        pending_notifications.put(msg)
        GLib.idle_add(notification_sender)

    notify_eavesdropper = DBusEavesdropper(session_bus,
                                           "org.freedesktop.Notifications",
                                           "Notify",
                                           on_notification)

    loop = GLib.MainLoop(GLib.main_context_default())
    if args.interactive:
        import IPython
        IPython.embed()
    else:
        CmdThread(AsteroidCmd(asteroid, loop)).start()
        loop.run()
