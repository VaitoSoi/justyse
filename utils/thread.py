import fnmatch
import logging as logging_
import threading

from . import logging
from .data import getitem_pattern


class Thread(threading.Thread):
    _stop_event: threading.Event

    def __init__(self,
                 target,
                 args: tuple = (),
                 kwargs: dict = None,
                 daemon: bool = True,
                 event: threading.Event = None):
        super(Thread, self).__init__(target=target, args=args, kwargs=kwargs or {}, daemon=daemon)
        self._stop_event = event

    def stop(self):
        if self._stop_event is not None:
            self._stop_event.set()

    def stopped(self):
        return (self._stop_event.is_set() if self._stop_event is not None else True) and self.is_alive()


class ThreadingManager:
    threads: dict[str, Thread] = {}
    timers: dict[str, threading.Timer] = {}
    lock = threading.Lock()
    logger: logging_.Logger

    def __init__(self):
        self.logger = logging_.getLogger("justyse.utils.thread_manager")
        self.logger.addHandler(logging.console_handler("Thread manager"))
        pass

    def __getitem__(self, item):
        if item.startswith('timer:'):
            if '*' in item:
                return getitem_pattern(self.timers, item[6:])
            else:
                return self.timers.get(item[6:])
        elif item.startswith('thread:'):
            if '*' in item:
                return getitem_pattern(self.threads, item[7:])
            else:
                return self.threads.get(item[7:])
        else:
            getattr(self, item)

    def create_thread(self,
                      name: str,
                      target: callable,
                      args: tuple = (),
                      kwargs: dict = None,
                      daemon: bool = True,
                      event: threading.Event = None,
                      start: bool = True) -> Thread:
        with self.lock:
            self.threads[name] = Thread(target=target,
                                        args=args,
                                        kwargs=kwargs or {},
                                        daemon=daemon,
                                        event=event)
            if start:
                self.threads[name].start()
            self.logger.debug(f"Created thread {name}")
            return self.threads[name]

    def close_thread(self, name: str, join: bool = True):
        with self.lock:
            if name in self.threads:
                thread = self.threads.pop(name)
                thread.stop()
                if join:
                    thread.join()
                self.threads.pop(name, None)
                self.logger.debug(f"Closed thread {name}")
            else:
                raise KeyError(name)

    def close_threads(self, pattern: str = '*', join: bool = True):
        # with self.lock:
        for name in self.threads.copy():
            if fnmatch.fnmatch(name, pattern):
                self.close_thread(name, join)

    def clear_threads(self, pattern: str = '*'):
        # with self.lock:
        for name in self.threads.copy():
            if fnmatch.fnmatch(name, pattern) and self.threads[name].stopped():
                self.close_thread(name, join=False)

    def create_timer(self,
                     name: str,
                     interval: float,
                     target: callable,
                     args: tuple = (),
                     kwargs: dict = None,
                     start: bool = True) -> threading.Timer:
        with self.lock:
            self.timers[name] = threading.Timer(interval=interval,
                                                function=target,
                                                args=args,
                                                kwargs=kwargs or {})
            if start:
                self.timers[name].start()
            self.logger.debug(f"Created timer {name}")
            return self.timers[name]

    def close_timer(self, name: str, join: bool = True):
        with self.lock:
            if name in self.timers:
                timer = self.timers.pop(name)
                timer.cancel()
                if join:
                    timer.join()
                self.timers.pop(name, None)
                self.logger.debug(f"Closed timer {name}")
            else:
                raise KeyError(name)

    def close_timers(self, pattern: str = '*', join: bool = True):
        # with self.lock:
        for name in self.timers.copy():
            if fnmatch.fnmatch(name, pattern):
                self.close_timer(name, join)

    def clear_timers(self, pattern: str = '*'):
        # with self.lock:
        for name in self.timers.copy():
            if fnmatch.fnmatch(name, pattern) and self.timers[name].finished.is_set():
                self.close_timer(name, join=False)
