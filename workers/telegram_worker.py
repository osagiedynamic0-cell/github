"""Telegram worker — fully debugged."""

import asyncio
import logging
import random
import hashlib
from datetime import datetime, timezone

from telethon import TelegramClient, errors

from config import (
    TELEGRAM_SESSION_1, TELEGRAM_API_ID_1, TELEGRAM_API_HASH_1,
    TELEGRAM_SESSION_2, TELEGRAM_API_ID_2, TELEGRAM_API_HASH_2,
    TELEGRAM_TOTAL_GROUPS, TELEGRAM_JOIN_PER_DAY,
    TELEGRAM_MIN_MEMBERS, TELEGRAM_POST_SPACING,
    TELEGRAM_SEARCH_KEYWORDS, TELEGRAM_BLACKLIST_KEYWORDS,
    TELEGRAM_GROUP_THRESHOLD, TELEGRAM_POSTS_WHEN_LOW,
    TELEGRAM_POSTS_WHEN_HIGH, is_telegram_peak_hour,
    OFFER_URL, PLATFORM_CHAR_LIMITS,
)
from supabase_client import SupabaseClient
from content_generator import generate_content

logger = logging.getLogger(__name__)

ACCOUNTS = [
    {"id": "account_1", "session": TELEGRAM_SESSION_1, "api_id": TELEGRAM_API_ID_1, "api_hash": TELEGRAM_API_HASH_1},
    {"id": "account_2", "session": TELEGRAM_SESSION_2, "api_id": TELEGRAM_API_ID_2, "api_hash": TELEGRAM_API_HASH_2},
]

class TelegramWorker:
    def __init__(self, supabase: SupabaseClient):
        self.supabase = supabase
        self.clients = {}
        self.blacklisted = set()
        self.failed = set()
        self.groups_joined = {"account_1": 0, "account_2": 0}

    async def _connect(self, account: dict):
        for attempt in range(3):
            try:
                client = TelegramClient(account["session"], account["api_id"], account["api_hash"])
                await client.connect()
                if await client.is_user_authorized():
                    return client
            except errors.FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 60))
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
        return None

    async def start(self):
        for acc in ACCOUNTS:
            if not acc["session"] or not acc["api_id"]:
                continue
            client = await self._connect(acc)
            if client:
                self.clients[acc["id"]] = client
                logger.info(f"Telegram {acc['id']} connected")
        return len(self.clients) > 0

    async def _discover_groups(self, account_id: str):
        if account_id not in self.clients:
            return []

        client = self.clients[account_id]
        found = []

        for keyword in TELEGRAM_SEARCH_KEYWORDS:
            if len(found) >= TELEGRAM_JOIN_PER_DAY:
                break

            try:
                async for dialog in client.iter_dialogs():
                    if not dialog.is_group or not dialog.entity:
                        continue

                    gid = str(dialog.entity.id)
                    if gid in self.blacklisted or gid in self.failed:
                        continue

                    title = (dialog.entity.title or "").lower()
                    if any(bad in title for bad in TELEGRAM_BLACKLIST_KEYWORDS):
                        self.blacklisted.add(gid)
                        continue

                    existing = self.supabase.get_active_groups(account_id)
                    if any(g.get("group_id") == gid for g in existing):
                        continue

                    try:
                        participants = await client.get_participants(dialog.entity, limit=0)
                        count = participants.total if hasattr(participants, 'total') else 0
                    except:
                        count = 0

                    if count >= TELEGRAM_MIN_MEMBERS:
                        found.append({"id": gid, "title": dialog.entity.title or "Unknown", "members": count})

                    if len(found) >= TELEGRAM_JOIN_PER_DAY:
                        break

            except errors.FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 60))
            except Exception as e:
                logger.warning(f"Search error: {e}")

        return found

    async def _join_group(self, account_id: str, group: dict) -> bool:
        if account_id not in self.clients:
            return False

        client = self.clients[account_id]
        gid = group["id"]

        try:
            entity = await client.get_entity(int(gid))

            # Check if already member
            dialogs = await client.get_dialogs()
            for d in dialogs:
                if d.entity and d.entity.id == entity.id:
                    self.supabase.add_group(gid, account_id, group["title"], group["members"])
                    self.groups_joined[account_id] += 1
                    return True

            await client.join_channel(entity)
            self.supabase.add_group(gid, account_id, group["title"], group["members"])
            self.groups_joined[account_id] += 1
            await asyncio.sleep(random.uniform(30, 90))
            return True

        except errors.AllowPaymentRequiredError:
            self.blacklisted.add(gid)
            self.supabase.blacklist_group(gid)
            return False
        except errors.InviteRequestRequiredError:
            self.failed.add(gid)
            return False
        except errors.FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            return False
        except Exception as e:
            logger.warning(f"Join failed for {group['title']}: {e}")
            self.failed.add(gid)
            return False

    async def _send_message(self, account_id: str, group_id: str, text: str) -> bool:
        if account_id not in self.clients:
            return False

        client = self.clients[account_id]

        for attempt in range(3):
            try:
                entity = await client.get_entity(int(group_id))
                if len(text) > PLATFORM_CHAR_LIMITS["telegram"]:
                    text = text[:3997] + "..."
                await client.send_message(entity, text, link_preview=True)
                await asyncio.sleep(random.uniform(*TELEGRAM_POST_SPACING))
                return True

            except errors.FloodWaitError as e:
                if e.seconds > 86400:
                    self.supabase.update_worker_state("telegram", {"status": "PAUSED", "last_error": f"FloodWait {e.seconds}s"})
                    return False
                await asyncio.sleep(min(e.seconds, 60))

            except errors.rpcerrorlist.ChatWriteForbiddenError:
                self.supabase.deactivate_group(group_id)
                self.failed.add(group_id)
                return False

            except errors.rpcerrorlist.UserBannedInChannelError:
                self.supabase.deactivate_group(group_id)
                self.failed.add(group_id)
                return False

            except errors.rpcerrorlist.SlowModeWaitError as e:
                await asyncio.sleep(e.seconds)

            except Exception:
                if attempt == 2:
                    self.failed.add(group_id)
                await asyncio.sleep(2)

        return False

    async def run_once(self) -> int:
        if not self.clients:
            if not await self.start():
                return 0

        # Daily reset
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.supabase.reset_daily_counters()

        state = self.supabase.get_worker_state("telegram")
        today_count = state.get("today_count", 0)
        total_sent = 0

        # Peak hours only
        if not is_telegram_peak_hour(datetime.now(timezone.utc).hour):
            return 0

        for account_id, client in self.clients.items():
            groups = self.supabase.get_active_groups(account_id)
            groups_count = len(groups)

            # Join new groups
            if groups_count < TELEGRAM_TOTAL_GROUPS // 2:
                new_groups = await self._discover_groups(account_id)
                for g in new_groups[:TELEGRAM_JOIN_PER_DAY]:
                    if await self._join_group(account_id, g):
                        groups_count += 1
                groups = self.supabase.get_active_groups(account_id)

            # Smart posting
            posts_per_group = get_telegram_posts_per_group(groups_count)
            daily_cap = posts_per_group * groups_count

            if today_count >= daily_cap:
                continue

            random.shuffle(groups)

            for group in groups[:posts_per_group]:
                if not group.get("is_active", True) or group["group_id"] in self.failed or group["group_id"] in self.blacklisted:
                    continue

                try:
                    audience = "freelancer" if random.random() < 0.5 else "affiliate"
                    content = generate_content("telegram", audience, True)
                    content_hash = hashlib.md5(content.encode()).hexdigest()

                    if self.supabase.is_content_posted(content_hash):
                        continue

                    if await self._send_message(account_id, group["group_id"], content):
                        self.supabase.mark_content_posted(content_hash, "telegram")
                        today_count += 1
                        total_sent += 1
                        self.supabase.update_worker_state("telegram", {"today_count": today_count})

                except Exception as e:
                    logger.error(f"Error: {e}")

        return total_sent

    async def run(self):
        logger.info("🚀 Starting Telegram worker")
        while True:
            try:
                await self.run_once()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Telegram error: {e}")
                await asyncio.sleep(60)
