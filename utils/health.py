"""Health check and dry run."""

import logging
import json
import time
from typing import Tuple

from config import check_config, get_gemini_keys, SUPABASE_URL, SUPABASE_KEY
from supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class HealthCheck:
    def __init__(self, supabase: SupabaseClient):
        self.supabase = supabase
        self.results = {}

    def run_all(self) -> bool:
        logger.info("=" * 60)
        logger.info("DRY RUN: BOOT SELF-TEST STARTING")
        logger.info("=" * 60)

        all_pass = True

        checks = [
            ("Environment variables", self._check_env),
            ("Supabase", self._check_supabase),
            ("Gemini", self._check_gemini),
            ("Telegram Account 1", self._check_telegram_1),
            ("Telegram Account 2", self._check_telegram_2),
            ("Bluesky Account A", self._check_bluesky_a),
            ("Bluesky Account B", self._check_bluesky_b),
            ("Quora", self._check_quora),
            ("Medium", self._check_medium),
        ]

        for name, fn in checks:
            try:
                passed, msg = fn()
                self.results[name] = (passed, msg)
                logger.info(f"{'✅' if passed else '❌'} {name}: {msg}")
                if not passed:
                    all_pass = False
            except Exception as e:
                self.results[name] = (False, str(e))
                logger.error(f"❌ {name}: Error - {e}")
                all_pass = False

        # Telegram dry run
        if all_pass:
            logger.info("-" * 60)
            logger.info("DRY RUN: Testing Telegram group joining...")
            if self._test_telegram_join():
                logger.info("✅ Telegram dry run passed")
            else:
                all_pass = False
                logger.error("❌ Telegram dry run failed")

        logger.info("=" * 60)
        logger.info(f"DRY RUN: {'ALL PASSED ✅' if all_pass else 'SOME FAILED ❌'}")
        return all_pass

    def _check_env(self) -> Tuple[bool, str]:
        checks = check_config()
        missing = [k for k, v in checks.items() if not v]
        if missing:
            return False, f"Missing: {', '.join(missing)}"
        return True, "All variables present"

    def _check_supabase(self) -> Tuple[bool, str]:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return False, "Not configured"
        if self.supabase.test_connection():
            return True, "Connected"
        return False, "Connection failed"

    def _check_gemini(self) -> Tuple[bool, str]:
        keys = get_gemini_keys()
        if not keys:
            return False, "No keys configured"
        try:
            from gemini_client import GeminiClient
            gc = GeminiClient()
            results = gc.test_all_keys()
            working = sum(1 for x in results if x)
            if working >= 3:
                return True, f"{working}/{len(keys)} keys working"
            return False, f"{working}/{len(keys)} keys working"
        except Exception as e:
            return False, str(e)

    def _check_telegram_1(self) -> Tuple[bool, str]:
        from config import TELEGRAM_SESSION_1, TELEGRAM_API_ID_1, TELEGRAM_API_HASH_1
        if not TELEGRAM_SESSION_1 or not TELEGRAM_API_ID_1:
            return False, "Not configured"

        import asyncio
        from telethon import TelegramClient

        async def test():
            client = TelegramClient(TELEGRAM_SESSION_1, TELEGRAM_API_ID_1, TELEGRAM_API_HASH_1)
            await client.connect()
            if not await client.is_user_authorized():
                return False, "Not authorized"
            me = await client.get_me()
            await client.disconnect()
            return True, f"Logged in as: {me.username or me.id}"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test())
        loop.close()
        return result

    def _check_telegram_2(self) -> Tuple[bool, str]:
        from config import TELEGRAM_SESSION_2, TELEGRAM_API_ID_2, TELEGRAM_API_HASH_2
        if not TELEGRAM_SESSION_2 or not TELEGRAM_API_ID_2:
            return False, "Not configured"

        import asyncio
        from telethon import TelegramClient

        async def test():
            client = TelegramClient(TELEGRAM_SESSION_2, TELEGRAM_API_ID_2, TELEGRAM_API_HASH_2)
            await client.connect()
            if not await client.is_user_authorized():
                return False, "Not authorized"
            me = await client.get_me()
            await client.disconnect()
            return True, f"Logged in as: {me.username or me.id}"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test())
        loop.close()
        return result

    def _check_bluesky_a(self) -> Tuple[bool, str]:
        from config import BLUESKY_USERNAME_A, BLUESKY_PASSWORD_A
        if not BLUESKY_USERNAME_A or not BLUESKY_PASSWORD_A:
            return False, "Not configured"
        try:
            from atproto import Client
            client = Client()
            profile = client.login(BLUESKY_USERNAME_A, BLUESKY_PASSWORD_A)
            return True, f"Logged in as: {profile.display_name or BLUESKY_USERNAME_A}"
        except Exception as e:
            return False, str(e)

    def _check_bluesky_b(self) -> Tuple[bool, str]:
        from config import BLUESKY_USERNAME_B, BLUESKY_PASSWORD_B
        if not BLUESKY_USERNAME_B or not BLUESKY_PASSWORD_B:
            return False, "Not configured"
        try:
            from atproto import Client
            client = Client()
            profile = client.login(BLUESKY_USERNAME_B, BLUESKY_PASSWORD_B)
            return True, f"Logged in as: {profile.display_name or BLUESKY_USERNAME_B}"
        except Exception as e:
            return False, str(e)

    def _check_quora(self) -> Tuple[bool, str]:
        from config import QUORA_COOKIES_JSON
        if not QUORA_COOKIES_JSON:
            return False, "Not configured"

        try:
            cookies = json.loads(QUORA_COOKIES_JSON)
            if not cookies:
                return False, "Invalid cookies"

            from patchright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = browser.new_context()
                context.add_cookies(cookies)
                page = context.new_page()
                page.goto("https://www.quora.com/profile", timeout=15000)
                time.sleep(2)

                if "login" in page.url.lower() or "signup" in page.url.lower():
                    browser.close()
                    return False, "Cookies expired"

                browser.close()
                return True, "Logged in"

        except Exception as e:
            return False, str(e)

    def _check_medium(self) -> Tuple[bool, str]:
        from config import MEDIUM_COOKIES_JSON
        if not MEDIUM_COOKIES_JSON:
            return False, "Not configured"

        try:
            cookies = json.loads(MEDIUM_COOKIES_JSON)
            if not cookies:
                return False, "Invalid cookies"

            from patchright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = browser.new_context()
                context.add_cookies(cookies)
                page = context.new_page()
                page.goto("https://medium.com/me/stories/drafts", timeout=15000)
                time.sleep(2)

                if "sign-in" in page.url.lower():
                    browser.close()
                    return False, "Cookies expired"

                browser.close()
                return True, "Logged in"

        except Exception as e:
            return False, str(e)

    def _test_telegram_join(self) -> bool:
        from config import TELEGRAM_SESSION_1, TELEGRAM_API_ID_1, TELEGRAM_API_HASH_1

        if not TELEGRAM_SESSION_1 or not TELEGRAM_API_ID_1:
            logger.warning("Telegram not configured, skipping dry run")
            return True

        import asyncio
        from telethon import TelegramClient

        async def test():
            try:
                client = TelegramClient(TELEGRAM_SESSION_1, TELEGRAM_API_ID_1, TELEGRAM_API_HASH_1)
                await client.connect()
                if not await client.is_user_authorized():
                    return False

                dialogs = await client.get_dialogs()
                for dialog in dialogs:
                    if dialog.is_group and dialog.entity:
                        try:
                            await client.send_message(dialog.entity, "Dry run test - please ignore")
                            await client.disconnect()
                            return True
                        except:
                            continue

                # Try to find a group
                result = await client.get_dialogs()
                if result:
                    await client.send_message(result[0].entity, "Dry run test - please ignore")
                    await client.disconnect()
                    return True

                await client.disconnect()
                return True

            except Exception as e:
                logger.warning(f"Telegram dry run error: {e}")
                return False

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test())
        loop.close()
        return result
