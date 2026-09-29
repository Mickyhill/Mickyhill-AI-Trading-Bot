# ==========================================
# MickyHill AI Trading Bot
# auto_scanner.py
#
# Runs scan_market() automatically every N seconds,
# alongside (not instead of) the Telegram-triggered
# manual scan. scan_market()'s own scan_lock already
# prevents the two from ever running at the same time
# — this thread just calls the same function on a timer.
# ==========================================

import threading


class AutoScanner(threading.Thread):
    def __init__(self, scan_callback, interval_seconds=900):
        super().__init__(daemon=True, name="auto-scanner")
        self.scan_callback = scan_callback
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        # Wait one interval before the FIRST auto-scan — main() already
        # does its own startup sequence (server time, wallet, etc.) and
        # the Telegram controller sends its own startup message; firing
        # an auto-scan immediately would race with that noise.
        while not self.stop_event.wait(self.interval_seconds):
            try:
                self.scan_callback(notify=True)
            except Exception as exc:
                print(f"⚠️ Auto-scan error: {exc}")