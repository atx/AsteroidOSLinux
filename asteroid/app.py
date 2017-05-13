
import cmd
import colorama
import functools
import logging
import queue
import sys
import threading
from gi.repository import GLib

import asteroid


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


class App:

    def __init__(self, address, cmd=True, verbose=False):
        self._setup_logging(verbose)
        self.asteroid = asteroid.Asteroid(address)
        self.loop = GLib.MainLoop()
        self.modules = []

    def _setup_logging(self, verbose):
        syslog = logging.StreamHandler(sys.stderr)
        formatter = LogFormatter()
        syslog.setFormatter(formatter)
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.logger.addHandler(syslog)

    def run(self):
        self.logger.info("Entering GLib event loop")
        self.loop.run()

    def register_module(self, module):
        module.register(self)
        # We don't really do anything with these yet, but just in case
        self.modules.append(module)
