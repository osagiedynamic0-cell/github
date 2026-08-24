"""Bluesky worker — fully debugged."""

import logging
import random
import time
import hashlib
from datetime import datetime, timezone

from atproto import Client, client_utils, exceptions

from config import (
    BLUESKY_USERNAME_A, BLUESKY_PASSWORD_A,
    BLUESKY_USERNAME_B, BLUESKY_PASSWORD_B,
    BLUESKY_POSTS_PER_ACCOUNT, BLUESKY_LINKS_PER_ACCOUNT,
    BLUESKY_POST_TIMES, OFFER_URL,
)
from supabase_client import SupabaseClient
from content_generator import generate_content

logger = logging.getLogger(__name__)

ACCOUNTS = [
    {"id": "bluesky_a", "username": BLUESKY_USERNAME_A, "password": BLUESKY_PASSWORD_A},
    {"id": "bluesky_b", "username": BLUESKY_USERNAME_B, "password": BLUESKY_PASSWORD_B},
]

class BlueskyWorker:
    def __init__(self, supabase: SupabaseClient):
        self.supabase = supabase
        self.clients = {}

    def _connect(self, account: dict):
        for attempt in range(3):
            try:
                client = Client()
                client.login(account["username"], account["password"])
                return client
            except exceptions.RateLimitError:
                time.sleep(60 * (attempt + 1))
            except Exception as e:
                logger.error(f"Bluesky connect error: {e}")
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        return None

    def start(self):
        for acc in ACCOUNTS:
            if not acc["username"] or not acc["password"]:
                continue
            client = self._connect(acc)
            if client:
                self.clients[acc["id"]] = client
                logger.info(f"Bluesky {acc['id']} connected")
        return len(self.clients) > 0

    def _post(self, client: Client, text: str, with_link: bool) -> bool:
        for attempt in range(3):
            try:
                if with_link:
                    builder = client_utils.TextBuilder()
                    builder.text(text)
                    builder.text("\n\n")
                    builder.link("check it out here", OFFER_URL)
                    client.send_post(builder)
                else:
                    client.send_post(text)
                return True
            except exceptions.RateLimitError:
                time.sleep(60 * (attempt + 1))
            except Exception as e:
                logger.error(f"Post error: {e}")
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        return False

    def run_once(self, current_hour: int) -> int:
        if not self.clients and not self.start():
            return 0

        if current_hour not in BLUESKY_POST_TIMES:
            return 0

        self.supabase.reset_daily_counters()
        state = self.supabase.get_worker_state("bluesky")
        today_count = state.get("today_count", 0)
        total_posts = 0

        for acc_id, client in self.clients.items():
            acc_state = self.supabase.get_worker_state(f"bluesky_{acc_id}")
            links_today = acc_state.get("links_today", 0)

            if today_count >= BLUESKY_POSTS_PER_ACCOUNT:
                continue

            with_link = links_today < BLUESKY_LINKS_PER_ACCOUNT and random.random() < 0.4

            audience = "freelancer" if random.random() < 0.5 else "affiliate"
            content = generate_content("bluesky", audience, with_link)
            content_hash = hashlib.md5(content.encode()).hexdigest()

            if self.supabase.is_content_posted(content_hash):
                continue

            if self._post(client, content, with_link):
                self.supabase.mark_content_posted(content_hash, "bluesky")
                today_count += 1
                total_posts += 1
                self.supabase.update_worker_state("bluesky", {"today_count": today_count})
                if with_link:
                    self.supabase.update_worker_state(f"bluesky_{acc_id}", {"links_today": links_today + 1})

            time.sleep(random.uniform(30, 90))

        return total_posts

    def run(self):
        logger.info("🚀 Starting Bluesky worker")
        while True:
            try:
                current_hour = datetime.now(timezone.utc).hour
                self.run_once(current_hour)
                time.sleep(60)
            except Exception as e:
                logger.error(f"Bluesky error: {e}")
                time.sleep(60)
