import os
import time
import json
import csv
import logging
import requests

from datetime import datetime
from zoneinfo import ZoneInfo

# تنظیمات
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
TIMEZONE = os.getenv("TIMEZONE", "Europe/Helsinki")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

session = requests.Session()


def telegram(method, data=None, timeout=60):
    response = session.post(
        f"{API}/{method}",
        data=data or {},
        timeout=timeout
    )
    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram API error"))

    return result["result"]


def send_message(text):
    if not ADMIN_CHAT_ID:
        logging.warning("ADMIN_CHAT_ID is not configured.")
        return

    try:
        telegram(
            "sendMessage",
            {
                "chat_id": ADMIN_CHAT_ID,
                "text": text
            },
            timeout=20
        )
    except Exception:
        logging.exception("Could not send notification")


def get_time(timestamp):
    dt = datetime.fromtimestamp(
        timestamp, ZoneInfo(TIMEZONE)
    )
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")


def save_event(row):
    filename = "events.csv"
    file_exists = os.path.exists(filename)

    with open(filename, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "Date", "Time", "Channel", "User ID",
                "Username", "Name", "Event"
            ])

        writer.writerow(row)


def status_is_member(status):
    return status in ("creator", "administrator", "member")


def process_update(update):
    # پیام شروع ربات
    message = update.get("message", {})

    if message.get("text", "").strip().split("@")[0] == "/start":
        chat_id = message["chat"]["id"]

        telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    f"ربات فعال است.\n"
                    f"شناسه عددی چت شما: {chat_id}\n\n"
                    "برای دریافت گزارش‌ها، این شناسه را "
                    "در متغیر ADMIN_CHAT_ID تنظیم کنید."
                )
            }
        )
        return

    # تغییر وضعیت عضویت
    change = update.get("chat_member")

    if not change:
        return

    old = change["old_chat_member"]
    new = change["new_chat_member"]

    old_status = old["status"]
    new_status = new["status"]

    user = new["user"]
    chat = change["chat"]

    # فقط خروج یا اخراج عضو
    if not status_is_member(old_status):
        return

    if new_status not in ("left", "kicked"):
        return

    event = "اخراج شده" if new_status == "kicked" else "کانال را ترک کرده"

    date, clock = get_time(change["date"])

    name = " ".join(
        part for part in [
            user.get("first_name", ""),
            user.get("last_name", "")
        ] if part
    ) or "بدون نام"

    username = (
        "@" + user["username"]
        if user.get("username")
        else "ندارد"
    )

    channel = chat.get("title", "کانال")
    user_id = user["id"]

    report = (
        "📢 گزارش خروج عضو\n\n"
        f"📌 کانال: {channel}\n"
        f"👤 نام: {name}\n"
        f"🔹 نام کاربری: {username}\n"
        f"🆔 شناسه: {user_id}\n"
        f"📅 تاریخ: {date}\n"
        f"🕒 ساعت: {clock}\n"
        f"📍 وضعیت: {event}"
    )

    logging.info(report.replace("\n", " | "))

    save_event([
        date, clock, channel, user_id,
        username, name, event
    ])

    send_message(report)


def main():
    # دریافت رویدادهای عضویت و پیام‌ها
    telegram("deleteWebhook", {"drop_pending_updates": "false"})

    offset = None

    logging.info("Bot started.")

    while True:
        try:
            params = {
                "timeout": 50,
                "allowed_updates": json.dumps([
                    "message",
                    "chat_member"
                ])
            }

            if offset is not None:
                params["offset"] = offset

            updates = telegram(
                "getUpdates",
                params,
                timeout=60
            )

            for update in updates:
                offset = update["update_id"] + 1

                try:
                    process_update(update)
                except Exception:
                    logging.exception("Could not process update")

        except KeyboardInterrupt:
            break
        except Exception:
            logging.exception("Polling failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
