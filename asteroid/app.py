
import cmd
import colorama
import functools
import logging
import queue
import sys
import threading
from gi.repository import GLib

import asteroid


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


class Cmd(cmd.Cmd):

    prompt = "[" + colorama.Fore.LIGHTBLUE_EX + "asteroid" + \
        colorama.Style.RESET_ALL + "] "

    def __init__(self, app):
        super(Cmd, self).__init__()
        self.asteroid = app.asteroid
        self.asteroid.dev.properties_changed.connect(self._changed_callback)
        self.loop = app.loop
        self.exiting = False
        self.logger = logging.getLogger()

    def _changed_callback(self, name, changed, lst):
        for k, v in changed.items():
            self.logger.debug("Changed %s = %s" % (k, v))

    @in_glib
    def do_battery(self, line):
        """ Fetches and prints the battery level """
        self.logger.info("Battery = %d" % self.asteroid.battery_level())

    @in_glib
    def do_update_time(self, line):
        """ Updates time on the watch """
        dt = None
        if line:
            dt = datetime.datetime.strptime(line, "%Y-%m-%d %T")
        self.asteroid.update_time(dt)
        if dt:
            self.logger.info("Set time to " + dt.isoformat(" "))
        else:
            self.logger.info("Set time local time")

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
        self.start_cmd = cmd

    def _setup_logging(self, verbose):
        syslog = logging.StreamHandler(sys.stderr)
        formatter = LogFormatter()
        syslog.setFormatter(formatter)
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.logger.addHandler(syslog)

    def _cmd_threadfn(self):
        self.cmd.cmdloop("")

    def run(self):
        if self.start_cmd:
            cmd = Cmd(self)
            def run():
                cmd.cmdloop("")
            thread = threading.Thread(target=run)
            thread.daemon = True
            thread.start()

        self.logger.info("Entering GLib event loop")
        self.loop.run()

    def register_module(self, module):
        module.register(self)
        # We don't really do anything with these yet, but just in case
        self.modules.append(module)
