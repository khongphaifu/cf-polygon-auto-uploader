import json
import logging
from typing import Optional
import requests
from config.settings import NotificationConfig
from core.exporter.excel_exporter import PolygonProblemRecord

logger = logging.getLogger(__name__)


class Notifier:
    """Handles optional notifications via Discord and Telegram."""

    def __init__(self, config: NotificationConfig):
        self.config = config

    def notify_problem_completed(self, record: PolygonProblemRecord) -> None:
        if not self.config.enabled:
            return

        # 1. Discord Webhook
        if self.config.discord_webhook_url:
            self._send_discord(record)

        # 2. Telegram Bot
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            self._send_telegram(record)

    def _send_discord(self, record: PolygonProblemRecord) -> None:
        try:
            color = 0x00FF00 if record.status == "SUCCESS" else 0xFF0000
            payload = {
                "username": "CF Polygon Uploader",
                "embeds": [
                    {
                        "title": f"🎉 [{record.name}] Bai tap da duoc nap thanh cong!",
                        "description": (
                            f"**Polygon Problem ID:** {record.id}\n"
                            f"**Trang thai Package:** {record.package_state}\n"
                            f"**Codeforces Import URL:** [Nhap vao Codeforces]({record.cf_import_url})\n"
                            f"**Link Polygon:** [Xem tren Polygon]({record.url})"
                        ),
                        "color": color,
                        "footer": {"text": "Automated by CF Polygon Auto Uploader"},
                    }
                ],
            }
            requests.post(self.config.discord_webhook_url, json=payload, timeout=5)
        except Exception as e:
            logger.warning(f"Loi gui Discord webhook: {e}")

    def _send_telegram(self, record: PolygonProblemRecord) -> None:
        try:
            token = self.config.telegram_bot_token
            chat_id = self.config.telegram_chat_id
            msg = (
                f"🎉 *Bai tap: {record.name}*\n"
                f"Polygon ID: `{record.id}`\n"
                f"Trang thai Package: *{record.package_state}*\n"
                f"CF Import URL: {record.cf_import_url}\n"
                f"Link Polygon: {record.url}"
            )
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except Exception as e:
            logger.warning(f"Loi gui Telegram message: {e}")

