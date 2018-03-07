"""Monitors management module."""
from functools import partial
from threading import Event, Thread


class RepeatingTimer(Thread):
    """A cyclic timer thread."""
    def __init__(self, cycle, func, *args, **kwargs):
        Thread.__init__(self)
        self.daemon = True
        self.cycle = cycle
        self.func = partial(func, *args, **kwargs)
        self.finished = Event()

    def run(self):
        while self.finished.is_set() is False:
            self.func()
            self.finished.wait(self.cycle)

    def cancel(self):
        self.finished.set()


class MonitorServer(object):
    """Monitors manager class, for activating and deactivating monitors."""
    MONITORS = {}

    @classmethod
    def register_monitor(cls, monitor, test):
        """Start monitor.

        Args:
            monitor (AbstractMonitor): monitor instance.
            test (object): test item instance.
        """
        timer = RepeatingTimer(monitor.CYCLE, monitor.safe_run_monitor, test)
        timer.start()
        cls.MONITORS[monitor] = timer

    @classmethod
    def unregister_monitor(cls, monitor):
        """Stop monitor.

        Args:
            monitor (AbstractMonitor): monitor instance.
        """
        if monitor not in cls.MONITORS:
            return

        thread = cls.MONITORS[monitor]
        thread.cancel()
        thread.join()
        cls.MONITORS.pop(monitor)