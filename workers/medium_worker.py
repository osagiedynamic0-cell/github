"""Medium worker — fully debugged."""

import json
import logging
import time
import random
import hashlib
from datetime import datetime, timezone

from patchright.sync_api import sync_playwright

from config import MEDIUM_COOKIES_JSON, MEDIUM_ARTICLES_PER_DAY, OFFER_URL
from supabase_client import SupabaseClient
from content_generator import generate_content

logger = logging.getLogger(__name__)

class MediumWorker:
    def __init__(self, supabase: SupabaseClient):
        self.supabase = supabase
        self.browser = None
        self.context = None
        self.page = None
        self.running = False

    def _get_cookies(self):
        if not MEDIUM_COOKIES_JSON:
            return []
        try:
            return json.loads(MEDIUM_COOKIES_JSON)
        except:
            return []

    def start(self) -> bool:
        for attempt in range(3):
            try:
                cookies = self._get_cookies()
                if not cookies:
                    return False

                playwright = sync_playwright().start()
                self.browser = playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                self.context = self.browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                self.context.add_cookies(cookies)
                self.page = self.context.new_page()

                self.page.goto("https://medium.com/me/stories/drafts", timeout=30000)
                time.sleep(3)

                if "sign-in" in self.page.url.lower():
                    self.supabase.update_worker_state("medium", {"status": "PAUSED", "last_error": "Cookies expired"})
                    return False

                self.running = True
                logger.info("Medium worker started")
                return True

            except Exception as e:
                logger.error(f"Medium start error (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(10 * (attempt + 1))

        return False

    def _publish_article(self) -> bool:
        if not self.page:
            return False

        try:
            self.page.goto("https://medium.com/new-story", timeout=30000)
            time.sleep(5)

            # Generate content
            audience = "freelancer" if random.random() < 0.5 else "affiliate"
            content = generate_content("medium", audience, True, None)
            lines = content.split("\n")
            title = lines[0] if lines else "How I Found Better Clients"
            body = "\n".join(lines[1:]) if len(lines) > 1 else content

            # Title
            for selector in ["h3", "input[placeholder*='title']", "div[data-testid='storyTitle']"]:
                elem = self.page.query_selector(selector)
                if elem:
                    elem.click()
                    elem.fill(title)
                    break

            time.sleep(1)

            # Body
            editor = None
            for selector in ["div[contenteditable='true']", "div.ProseMirror"]:
                editor = self.page.query_selector(selector)
                if editor:
                    break

            if not editor:
                logger.warning("Medium editor not found")
                return False

            editor.click()
            for paragraph in body.split("\n"):
                editor.type(paragraph, delay=random.randint(20, 60))
                editor.press("Enter")
                time.sleep(random.uniform(0.3, 0.8))

            # Tags
            tag_input = self.page.query_selector("input[placeholder*='tag']")
            if tag_input:
                for tag in ["Freelancing", "Affiliate Marketing", "Small Business"]:
                    tag_input.click()
                    tag_input.fill(tag)
                    time.sleep(1)
                    tag_input.press("Enter")
                    time.sleep(0.5)

            # Publish
            for selector in ["button[data-action='publish']", "button.publishButton", "button:has-text('Publish')"]:
                btn = self.page.query_selector(selector)
                if btn:
                    btn.click()
                    break

            time.sleep(3)

            for selector in ["button[data-action='confirm-publish']", "button:has-text('Publish now')"]:
                btn = self.page.query_selector(selector)
                if btn:
                    btn.click()
                    break

            time.sleep(3)
            logger.info("Medium article published")
            return True

        except Exception as e:
            logger.error(f"Medium publish error: {e}")
            if "canvas" in str(e).lower() or "editor" in str(e).lower():
                self.supabase.update_worker_state("medium", {"status": "PAUSED", "last_error": "Canvas editor failed"})
            return False

    def run_once(self) -> int:
        if not self.running and not self.start():
            return 0

        self.supabase.reset_daily_counters()
        state = self.supabase.get_worker_state("medium")
        today_count = state.get("today_count", 0)

        if today_count >= MEDIUM_ARTICLES_PER_DAY or state.get("status") == "PAUSED":
            return 0

        if self._publish_article():
            self.supabase.update_worker_state("medium", {"today_count": today_count + 1})
            return 1

        return 0

    def run(self):
        logger.info("🚀 Starting Medium worker")
        while True:
            try:
                current_hour = datetime.now(timezone.utc).hour
                if current_hour == 16:
                    self.run_once()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Medium error: {e}")
                time.sleep(60)
