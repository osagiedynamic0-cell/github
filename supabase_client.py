"""Supabase state storage with connection retry."""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self._client = None
        self._connected = False
        self._memory_store: Dict[str, Any] = {}

        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.warning("Supabase not configured - using in-memory fallback")
            return

        self._connect()

    def _connect(self) -> bool:
        for attempt in range(5):
            try:
                self._client = create_client(SUPABASE_URL, SUPABASE_KEY)
                # Test connection with a simple query
                self._client.table("worker_state").select("count", count="exact").limit(1).execute()
                self._connected = True
                logger.info("Supabase connected")
                return True
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Supabase connection attempt {attempt + 1} failed: {e}")
                if attempt < 4:
                    time.sleep(wait)
        self._connected = False
        logger.error("Failed to connect to Supabase")
        return False

    def test_connection(self) -> bool:
        """Test if Supabase is connected."""
        if not self._client:
            return False
        try:
            self._client.table("worker_state").select("count", count="exact").limit(1).execute()
            self._connected = True
            return True
        except Exception:
            # Try to reconnect
            return self._connect()

    def _execute(self, operation, *args, **kwargs):
        for attempt in range(3):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def get_worker_state(self, platform: str) -> Dict[str, Any]:
        if not self._client or not self._connected:
            return self._memory_store.get(f"state_{platform}", {"platform": platform, "today_count": 0, "status": "RUNNING"})

        try:
            result = self._execute(
                lambda: self._client.table("worker_state").select("*").eq("platform", platform).execute()
            )
            if result and result.data:
                return result.data[0]
        except Exception:
            pass
        return {"platform": platform, "today_count": 0, "status": "RUNNING"}

    def update_worker_state(self, platform: str, updates: Dict[str, Any]):
        if not self._client or not self._connected:
            key = f"state_{platform}"
            if key not in self._memory_store:
                self._memory_store[key] = {"platform": platform}
            self._memory_store[key].update(updates)
            return

        try:
            existing = self.get_worker_state(platform)
            if existing.get("platform"):
                self._execute(lambda: self._client.table("worker_state").update(updates).eq("platform", platform).execute())
            else:
                data = {"platform": platform, **updates}
                self._execute(lambda: self._client.table("worker_state").insert(data).execute())
        except Exception as e:
            logger.warning(f"Error updating worker state: {e}")

    def is_content_posted(self, content_hash: str) -> bool:
        if not self._client or not self._connected:
            return content_hash in self._memory_store.get("posted", set())

        try:
            result = self._execute(
                lambda: self._client.table("posted_content").select("content_hash").eq("content_hash", content_hash).execute()
            )
            return result and len(result.data) > 0
        except Exception:
            return False

    def mark_content_posted(self, content_hash: str, platform: str):
        if not self._client or not self._connected:
            posted = self._memory_store.setdefault("posted", set())
            posted.add(content_hash)
            return

        try:
            self._execute(
                lambda: self._client.table("posted_content").insert({
                    "content_hash": content_hash,
                    "platform": platform,
                }).execute()
            )
        except Exception as e:
            logger.warning(f"Error marking content: {e}")

    def get_active_groups(self, account_id: str = None) -> List[Dict[str, Any]]:
        if not self._client or not self._connected:
            return list(self._memory_store.get("groups", {}).values())

        try:
            query = self._client.table("telegram_groups").select("*").eq("is_active", True)
            if account_id:
                query = query.eq("account_id", account_id)
            result = self._execute(lambda: query.execute())
            return result.data if result and result.data else []
        except Exception:
            return []

    def add_group(self, group_id: str, account_id: str, title: str = "", members: int = 0):
        if not self._client or not self._connected:
            groups = self._memory_store.setdefault("groups", {})
            groups[group_id] = {"group_id": group_id, "account_id": account_id, "is_active": True}
            return

        try:
            self._execute(
                lambda: self._client.table("telegram_groups").upsert({
                    "group_id": group_id,
                    "account_id": account_id,
                    "is_active": True,
                    "group_title": title,
                    "member_count": members,
                }).execute()
            )
        except Exception as e:
            logger.warning(f"Error adding group: {e}")

    def deactivate_group(self, group_id: str):
        if not self._client or not self._connected:
            groups = self._memory_store.get("groups", {})
            if group_id in groups:
                groups[group_id]["is_active"] = False
            return

        try:
            self._execute(lambda: self._client.table("telegram_groups").update({"is_active": False}).eq("group_id", group_id).execute())
        except Exception as e:
            logger.warning(f"Error deactivating group: {e}")

    def blacklist_group(self, group_id: str):
        self.deactivate_group(group_id)
        logger.info(f"Group {group_id} blacklisted")

    def reset_daily_counters(self):
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for platform in ["telegram", "bluesky", "quora", "medium"]:
            state = self.get_worker_state(platform)
            if state.get("last_reset_date") != current_date:
                self.update_worker_state(platform, {
                    "today_count": 0,
                    "links_today": 0,
                    "last_reset_date": current_date,
                })
