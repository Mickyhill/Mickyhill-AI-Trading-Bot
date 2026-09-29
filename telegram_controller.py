# ==========================================
# MickyHill AI Trading Bot
# telegram_controller.py
# Telegram polling/control interface.
# ==========================================

import os
import threading
import time
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BOT_NAME
from notifier import send_message
from paper_db import get_open_trades, get_all_trades, export_csv, set_state
import time


BUTTONS = [
    ["🔍 Scan Market", "📊 Best Trade"],
    ["📈 Active Trades", "📋 Trade History"],
    ["📥 Export Data", "⚙️ Bot Status"],
    ["🔄 Reset Circuit Breaker"],
]


class TelegramController(threading.Thread):
    def __init__(self, scan_callback):
        super().__init__(daemon=True, name="telegram-controller")
        self.scan_callback = scan_callback
        self.stop_event = threading.Event()
        self.offset = None

    def stop(self):
        self.stop_event.set()

    @property
    def base_url(self):
        return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    def _send_keyboard(self, chat_id, text):
        if not TELEGRAM_BOT_TOKEN:
            return
        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "reply_markup": {"keyboard": BUTTONS, "resize_keyboard": True},
                },
                timeout=20,
            ).raise_for_status()
        except Exception as exc:
            print(f"❌ Telegram controller send error: {exc}")

    def _allowed(self, chat_id):
        return bool(TELEGRAM_CHAT_ID) and str(chat_id) == str(TELEGRAM_CHAT_ID)

    def _handle(self, chat_id, text):
        if not self._allowed(chat_id):
            return
        command = (text or "").strip().lower()
        if command in ("/start", "/help"):
            self._send_keyboard(chat_id, f"🤖 {BOT_NAME}\n\nChoose an action:")
            return
        if command in ("🔍 scan market", "/scan", "scan"):
            send_message("🔎 Scan requested from Telegram. Scanning Bybit now...")
            threading.Thread(target=self.scan_callback, kwargs={"notify": True}, daemon=True).start()
            return
        if command in ("📊 best trade", "/best", "best"):
            threading.Thread(target=self.scan_callback, kwargs={"notify": True}, daemon=True).start()
            return
        if command in ("📈 active trades", "/active", "active"):
            trades = get_open_trades()
            if not trades:
                send_message("📈 ACTIVE TRADES\n\nNo open paper trades.")
                return
            lines = ["📈 ACTIVE PAPER TRADES\n"]
            for t in trades:
                lines.append(
                    f"{t['symbol']} {t['direction']} | Entry {t['entry']} | "
                    f"Hit: {', '.join(t.get('targets_hit', [])) or 'None'} | Status {t['status']}"
                )
            send_message("\n".join(lines))
            return
        if command in ("📋 trade history", "/history", "history"):
            trades = get_all_trades(limit=10)
            if not trades:
                send_message("📋 TRADE HISTORY\n\nNo trades recorded yet.")
                return
            lines = ["📋 LAST 10 PAPER TRADES\n"]
            for t in trades:
                result = t.get("final_result") or t.get("status")
                lines.append(f"{t['symbol']} {t['direction']} | {result} | Entry {t['entry']} | Exit {t.get('exit_price') or '-'}")
            send_message("\n".join(lines))
            return
        if command in ("📥 export data", "/export", "export"):
            path = export_csv()
            try:
                with open(path, "rb") as f:
                    requests.post(
                        f"{self.base_url}/sendDocument",
                        data={"chat_id": chat_id},
                        files={"document": (os.path.basename(path), f, "text/csv")},
                        timeout=30,
                    ).raise_for_status()
            except Exception as exc:
                print(f"❌ Telegram export error: {exc}")
                send_message(f"❌ Could not export trade data: {exc}")
            return
        if command in ("⚙️ bot status", "/status", "status"):
            active = len(get_open_trades())
            total = len(get_all_trades())
            send_message(
                f"⚙️ {BOT_NAME}\n\n"
                f"Paper Trading: ON\n"
                f"Live Trading: OFF\n"
                f"Active Paper Trades: {active}\n"
                f"Stored Trades: {total}\n"
                f"Telegram Control: ON\n"
                f"Paper Monitor: ON"
            )
            return
        if command in ("🔄 reset circuit breaker", "/resetbreaker", "resetbreaker"):
            # Testing/paper-trading convenience only: clears the
            # consecutive-loss and daily-loss streak by excluding every
            # trade closed up to now from future circuit-breaker checks.
            # This does NOT undo or hide the trades themselves — history
            # and stats are untouched, this only affects whether the
            # breaker treats them as part of an active losing streak.
            set_state("circuit_breaker_reset_at", str(int(time.time())))
            send_message(
                "🔄 Circuit breaker manually reset.\n\n"
                "The consecutive-loss streak has been cleared as of now. "
                "Trade history is unchanged — this only affects future "
                "circuit-breaker checks.\n\n"
                "⚠️ This is a testing convenience. Do not rely on manual "
                "resets once real capital is involved — let the breaker "
                "run its course in live trading."
            )
            return

    def run(self):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("⚠️ Telegram controller disabled: credentials missing")
            return
        print("🤖 Telegram controller started")
        self._send_keyboard(TELEGRAM_CHAT_ID, f"🤖 {BOT_NAME}\n\nTelegram control is online.")
        while not self.stop_event.is_set():
            try:
                response = requests.get(
                    f"{self.base_url}/getUpdates",
                    params={"timeout": 25, "offset": self.offset},
                    timeout=35,
                )
                response.raise_for_status()
                data = response.json()
                for update in data.get("result", []):
                    self.offset = update["update_id"] + 1
                    message = update.get("message") or {}
                    chat = message.get("chat") or {}
                    self._handle(chat.get("id"), message.get("text", ""))
            except Exception as exc:
                print(f"❌ Telegram polling error: {exc}")
                self.stop_event.wait(5)