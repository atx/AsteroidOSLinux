#! /usr/bin/env python3

import argparse
import colorama
import datetime
import pydbus as dbus
import queue
import cmd
import threading
import functools
import logging
import yaml
import os
import sys
from gi.repository import GLib
from asteroid.module import *
from asteroid import *


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
        self.logger = logging.getLogger()

    def _changed_callback(self, name, changed, lst):
        for k, v in changed.items():
            self.logger.debug("Changed %s = %s" % (k, v))

    @in_glib
    def do_battery(self, line):
        """ Fetches and prints the battery level """
        logger.info("Battery = %d" % self.asteroid.battery_level())

    @in_glib
    def do_update_time(self, line):
        """ Updates time on the watch """
        dt = None
        if line:
            dt = datetime.datetime.strptime(line, "%Y-%m-%d %T")
        self.asteroid.update_time(dt)
        if dt:
            logger.info("Set time to " + dt.isoformat(" "))
        else:
            logger.info("Set time local time")

    def do_ipython(self, line):
        import IPython
        IPython.embed()

    def do_exit(self, line):
        self.loop.quit()
        self.exiting = True

    do_EOF = do_exit

    def emptyline(self):
        pass

    def postcmd(self, stop, line):
        return self.exiting


class CmdThread(threading.Thread):

    def __init__(self, cmd):
        super(CmdThread, self).__init__()
        self.cmd = cmd

    def run(self):
        self.cmd.cmdloop("")


class LogFormatter(logging.Formatter):

    @staticmethod
    @functools.lru_cache(10)
    def _prefix(prefix, color):
        return colorama.Style.RESET_ALL + "[" + color + prefix + \
            colorama.Style.RESET_ALL + "]"

    _namecolors = {
        "DEBUG": ("DBG", colorama.Fore.LIGHTWHITE_EX),
        "INFO": ("INF", colorama.Fore.LIGHTBLUE_EX),
        "WARNING": ("WRN", colorama.Fore.LIGHTYELLOW_EX),
        "ERROR": ("ERR", colorama.Fore.LIGHTRED_EX),
        "CRITICAL": ("CRT", colorama.Fore.LIGHTRED_EX),
        "UNKNOWN": ("???", colorama.Fore.LIGHTWHITE_EX)
    }

    def format(self, record):
        prefix = LogFormatter._prefix(
                    *LogFormatter._namecolors.get(
                                    record.levelname,
                                    LogFormatter._namecolors["DEBUG"]))
        return prefix + " " + super(LogFormatter, self).format(record)


def setup_logging(verbose):
    syslog = logging.StreamHandler(sys.stderr)
    formatter = LogFormatter()
    syslog.setFormatter(formatter)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(syslog)
    return logger


# We want to have this in string form so we can auto-create a
# (nicely formatted) config later
default_config_str = """
asteroid:
    address: "SET_ME"

modules:
    timesync: {}
    reconnect: {}
    notify: {}
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AsteroidOSLinux")
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Drop to IPython shell instead of GLib event loop"
    )
    parser.add_argument(
        "-c", "--config",
        default="~/.config/asteroidoslinux/config.yaml",
        type=os.path.expanduser,
        help="Set config file path"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug output"
    )
    parser.add_argument(
        "--rewrite-default-config",
        action="store_true",
        help="Overwrite the config file with the default configuration"
    )

    args = parser.parse_args()
    logger = setup_logging(verbose=args.verbose)

    if not os.path.exists(args.config) or args.rewrite_default_config:
        os.makedirs(os.path.dirname(args.config), exist_ok=True)
        with open(args.config, "w") as f:
            f.write(default_config_str)
        logger.info("Created new config file in %s" % os.path.abspath(args.config))

    with open(args.config) as f:
        config = yaml.load(f)

    logger.info("Loaded config file from %s" % os.path.abspath(args.config))

    logger.info("Using device address %s" % config["asteroid"]["address"])
    session_bus = dbus.SessionBus()
    asteroid = Asteroid(config["asteroid"]["address"])

    modules = []
    for modname in [n for n in config["modules"]]:
        if modname not in MetaModule.registry:
            logger.error("Module %s not known!" % modname)
            sys.exit(-1)
        modules.append(MetaModule.registry[modname](asteroid,
                                                    config["modules"][modname]))

    logger.info("Loaded modules %s" % ", ".join(map(lambda m: m.name, modules)))

    loop = GLib.MainLoop(GLib.main_context_default())
    if args.interactive:
        import IPython
        IPython.embed()
    else:
        CmdThread(AsteroidCmd(asteroid, loop)).start()
        loop.run()
