#! /usr/bin/env python3

import argparse
import pydbus as dbus
import queue
from gi.repository import GLib
from asteroid import *

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
            print("Notification %s " % msg)
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
        print("Entering the event loop")
        loop.run()
