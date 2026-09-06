"""One serialized state owner; websocket callbacks enqueue without broker I/O."""
from queue import Queue, Empty
from threading import Thread
import time
from db.logger import set_status


class TradingWorker:
    def __init__(self, trader):
        self.trader = trader
        self.events = Queue()
        self.stopping = False
        self.thread = Thread(target=self._run, name='trading-worker', daemon=True)

    def start(self):
        self.thread.start()

    def on_minute_bar(self, *args):
        self.events.put(args)

    def _run(self):
        next_tick = 0
        while not self.stopping or not self.events.empty():
            try:
                args = self.events.get(timeout=0.2)
            except Empty:
                args = None
            try:
                if args:
                    self.trader.on_minute_bar(*args)
                if time.monotonic() >= next_tick:
                    self.trader.tick()
                    next_tick = time.monotonic() + 5
            except Exception as exc:
                self.trader.broker.blocked = str(exc)
                set_status(self.trader.scope, 'blocked', str(exc), db_path=self.trader.db_path)
            finally:
                if args:
                    self.events.task_done()

    def stop(self):
        self.stopping = True
        self.thread.join(timeout=15)
        set_status(self.trader.scope, 'stopped' if not self.thread.is_alive() else 'unresolved',
                   'Process stopping; confirmed positions retained', db_path=self.trader.db_path)
