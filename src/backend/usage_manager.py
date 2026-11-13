"""Editable model pricing and local API usage history."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import copy
from datetime import date, datetime, timedelta, timezone

from src.utils.paths import Paths


DEFAULT_TABLES = {
    "version": 3,
    "prices": [],
    "rpd_tracking": {},
}

# Migration fingerprints only: these identify and remove version-1 sample rows.
# They are never loaded as active prices or limits.
LEGACY_DEFAULT_PRICES = [
    {"provider": "ollama", "model": "gemma4", "plan": "any", "input_usd_per_million": 0.14,
     "cached_input_usd_per_million": 0.05, "output_usd_per_million": 0.40},
    {"provider": "gemini", "model": "gemini-3.1-flash-lite", "plan": "free", "input_usd_per_million": 0.0,
     "cached_input_usd_per_million": None, "output_usd_per_million": 0.0},
    {"provider": "gemini", "model": "gemini-3.1-flash-lite", "plan": "paid", "input_usd_per_million": 0.25,
     "cached_input_usd_per_million": 0.025, "output_usd_per_million": 1.50},
]


class UsageManager:
    """Stores editable prices, a local Gemini RPD meter, and request metrics."""

    _lock = threading.RLock()

    def __init__(self):
        self.tables_path = os.path.join(Paths.CACHE, "pricing_tables.json")
        self.history_path = os.path.join(Paths.CACHE, "usage_history.json")
        # UI refreshes query the same files repeatedly. Keep parsed JSON in memory
        # and reload only when another operation changes the file on disk.
        self._json_cache: dict[str, tuple[tuple[int, int], object]] = {}

    def _read_cached_json(self, path: str, default):
        """Read JSON once per on-disk version, using mtime and size for invalidation."""
        try:
            stat = os.stat(path)
            signature = (stat.st_mtime_ns, stat.st_size)
            cached = self._json_cache.get(path)
            if cached and cached[0] == signature:
                return cached[1]
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            self._json_cache[path] = (signature, data)
            return data
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            self._json_cache.pop(path, None)
            return default

    @staticmethod
    def _atomic_json_write(path: str, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(prefix="mts_usage_", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def load_tables(self) -> dict:
        data = copy.deepcopy(DEFAULT_TABLES)
        needs_migration = False
        saved_version = 1
        try:
            saved = self._read_cached_json(self.tables_path, {})
            if isinstance(saved, dict):
                saved_version = int(saved.get("version", 1) or 1)
                if isinstance(saved.get("prices"), list):
                    data["prices"] = saved["prices"]
                if isinstance(saved.get("rpd_tracking"), dict):
                    data["rpd_tracking"] = saved["rpd_tracking"]
                needs_migration = int(saved.get("version", 1) or 1) < 3
        except FileNotFoundError:
            needs_migration = True
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        if needs_migration:
            if saved_version < 2:
                data["prices"] = self._remove_known_defaults(data["prices"], LEGACY_DEFAULT_PRICES)
            self._atomic_json_write(self.tables_path, data)
        return data

    @staticmethod
    def _remove_known_defaults(rows: list[dict], defaults: list[dict]) -> list[dict]:
        """Remove only the exact sample rows shipped by version 1; keep user-edited values."""
        return [
            row for row in rows
            if not any(isinstance(row, dict) and row == default for default in defaults)
        ]

    def save_tables(self, data: dict):
        cleaned = {
            "version": 3,
            "prices": data.get("prices", []),
            "rpd_tracking": data.get("rpd_tracking", {}),
        }
        with self._lock:
            self._atomic_json_write(self.tables_path, cleaned)
            self._json_cache.pop(self.tables_path, None)

    def save_prices(self, prices: list[dict]):
        """Update price rows without overwriting RPD counters written by background requests."""
        with self._lock:
            data = self.load_tables()
            data["prices"] = prices
            self.save_tables(data)

    def export_prices(self, path: str, prices: list[dict] | None = None):
        payload = {"version": 2, "prices": prices if prices is not None else self.load_tables()["prices"]}
        self._atomic_json_write(path, payload)

    def import_prices(self, path: str) -> list[dict]:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        rows = data.get("prices") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("The price file must contain a 'prices' list.")
        cleaned = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("provider") or not row.get("model"):
                raise ValueError("Every price row needs provider and model values.")
            plan = str(row.get("plan", "any")).strip().lower() or "any"
            if plan not in ("any", "free", "paid", "off-peak"):
                raise ValueError("Price plans must be any, free, paid, or off-peak.")
            cleaned.append({
                "provider": str(row["provider"]).strip().lower(),
                "model": str(row["model"]).strip(),
                "plan": plan,
                "input_usd_per_million": self._optional_number(row.get("input_usd_per_million")),
                "cached_input_usd_per_million": self._optional_number(row.get("cached_input_usd_per_million")),
                "output_usd_per_million": self._optional_number(row.get("output_usd_per_million")),
            })
        return cleaned

    @staticmethod
    def _number(value, default=0.0) -> float:
        try:
            number = float(value)
            return number if math.isfinite(number) and number >= 0 else default
        except (TypeError, ValueError):
            return default

    @classmethod
    def _optional_number(cls, value):
        if value is None or str(value).strip().lower() in ("", "not configured", "n/a", "-"):
            return None
        return cls._number(value, 0.0)

    @staticmethod
    def _matches(table_model: str, requested_model: str) -> bool:
        table_key = str(table_model).strip().lower()
        requested_key = str(requested_model).strip().lower()
        return bool(table_key and (requested_key == table_key or requested_key.startswith(table_key + ":") or requested_key.startswith(table_key + "-")))

    def get_price(self, provider: str, model: str, plan: str | None = None):
        tables = self.load_tables()
        if plan:
            active_plan = plan
        elif provider.lower() == "gemini":
            active_plan = "paid"
        elif provider.lower() == "ollama" and self._is_ollama_off_peak():
            active_plan = "off-peak"
        else:
            active_plan = "any"
        candidates = [
            row for row in tables["prices"]
            if str(row.get("provider", "")).lower() == provider.lower()
            and self._matches(row.get("model", ""), model)
            and row.get("plan", "any") in (active_plan, "any")
        ]
        candidates.sort(key=lambda row: (row.get("plan") != active_plan, -len(str(row.get("model", "")))))
        if not candidates and provider.lower() == "gemini":
            candidates = [
                row for row in tables["prices"]
                if str(row.get("provider", "")).lower() == "gemini"
                and self._matches(row.get("model", ""), model)
                and row.get("plan", "any") == "free"
            ]
            candidates.sort(key=lambda row: -len(str(row.get("model", ""))))
        return candidates[0] if candidates else None

    @staticmethod
    def _is_ollama_off_peak(now: datetime | None = None) -> bool:
        """Ollama off-peak is outside 12:00–18:00 UTC on weekdays and all weekend."""
        now = now or datetime.now(timezone.utc)
        return now.weekday() >= 5 or not (12 <= now.hour < 18)

    def calculate_cost(self, provider: str, model: str, usage: dict, plan: str | None = None):
        price = self.get_price(provider, model, plan)
        if not price:
            return None
        input_rate = self._optional_number(price.get("input_usd_per_million"))
        output_rate = self._optional_number(price.get("output_usd_per_million"))
        if input_rate is None or output_rate is None:
            return None
        input_tokens = max(0, int(usage.get("prompt_tokens", 0) or 0))
        cached_tokens = min(input_tokens, max(0, int(usage.get("cache_tokens", 0) or 0)))
        output_tokens = max(0, int(usage.get("output_tokens", 0) or 0))
        output_tokens += max(0, int(usage.get("thought_tokens", 0) or 0))
        input_price = input_rate
        cache_price = self._optional_number(price.get("cached_input_usd_per_million"))
        if cache_price is None:
            cache_price = input_price
        return (
            ((input_tokens - cached_tokens) * input_price)
            + (cached_tokens * cache_price)
            + (output_tokens * output_rate)
        ) / 1_000_000

    def get_gemini_rpd(self, connection_profile_id: str, model: str) -> dict:
        """Return the configured daily cap and current manual/app usage for this connection/model."""
        today = self.pacific_today().isoformat()
        tables = self.load_tables()
        profiles = tables.get("rpd_tracking", {})
        profile = profiles.get(connection_profile_id or "legacy", {}) if isinstance(profiles, dict) else {}
        state = profile.get(model, {}) if isinstance(profile, dict) else {}
        if not isinstance(state, dict):
            state = {}
        return {
            "limit": self._nonnegative_int(state.get("limit")),
            "used": self._nonnegative_int(state.get("used")) if state.get("date") == today else 0,
            "date": today,
        }

    @staticmethod
    def _nonnegative_int(value) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def set_gemini_rpd(self, connection_profile_id: str, model: str, limit: int, used: int):
        limit = int(limit)
        used = int(used)
        if limit < 0 or used < 0:
            raise ValueError("RPD values cannot be negative.")
        with self._lock:
            tables = self.load_tables()
            profiles = tables.setdefault("rpd_tracking", {})
            profile = profiles.setdefault(connection_profile_id or "legacy", {})
            profile[model] = {"limit": limit, "used": used, "date": self.pacific_today().isoformat()}
            self.save_tables(tables)

    def _increment_gemini_rpd_locked(self, connection_profile_id: str, model: str, requests: int):
        if requests <= 0 or not model:
            return
        today = self.pacific_today().isoformat()
        tables = self.load_tables()
        profiles = tables.setdefault("rpd_tracking", {})
        profile = profiles.setdefault(connection_profile_id or "legacy", {})
        state = profile.get(model, {})
        if not isinstance(state, dict):
            state = {}
        used = self._nonnegative_int(state.get("used")) if state.get("date") == today else 0
        profile[model] = {
            "limit": self._nonnegative_int(state.get("limit")),
            "used": used + requests,
            "date": today,
        }
        self.save_tables(tables)

    def record_usage(self, provider: str, model: str, usage: dict, connection_profile_id: str = "") -> float | None:
        usage = usage or {}
        cost = self.calculate_cost(provider, model, usage)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider.lower(),
            "connection_profile_id": connection_profile_id or "legacy",
            "model": model,
            "requests": max(1, int(usage.get("request_count", 1) or 1)),
            "input_tokens": max(0, int(usage.get("prompt_tokens", 0) or 0)),
            "cached_input_tokens": max(0, int(usage.get("cache_tokens", 0) or 0)),
            "cache_reported": "cache_tokens" in usage,
            "output_tokens": max(0, int(usage.get("output_tokens", 0) or 0)),
            "thinking_tokens": max(0, int(usage.get("thought_tokens", 0) or 0)),
            "cost_usd": cost,
        }
        with self._lock:
            try:
                with open(self.history_path, "r", encoding="utf-8") as stream:
                    history = json.load(stream)
                if not isinstance(history, list):
                    history = []
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                history = []
            history.append(event)
            self._atomic_json_write(self.history_path, history[-10000:])
            self._json_cache.pop(self.history_path, None)
            if provider.lower() == "gemini":
                self._increment_gemini_rpd_locked(
                    connection_profile_id or "legacy", model, event["requests"]
                )
        return cost

    def load_history(self) -> list[dict]:
        """Return parsed usage rows, re-reading the file only after it changes."""
        with self._lock:
            data = self._read_cached_json(self.history_path, [])
            return data if isinstance(data, list) else []

    def clear_history(self):
        """Delete recorded request history without changing prices or Gemini RPD counters."""
        with self._lock:
            self._atomic_json_write(self.history_path, [])
            self._json_cache.pop(self.history_path, None)

    @staticmethod
    def pacific_today(now: datetime | None = None) -> date:
        now = now or datetime.now(timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            return now.astimezone(ZoneInfo("America/Los_Angeles")).date()
        except Exception:
            year = now.year
            march_first = date(year, 3, 1)
            march_second_sunday = 1 + ((6 - march_first.weekday()) % 7) + 7
            november_first = date(year, 11, 1)
            november_first_sunday = 1 + ((6 - november_first.weekday()) % 7)
            dst_start = datetime(year, 3, march_second_sunday, 10, tzinfo=timezone.utc)
            dst_end = datetime(year, 11, november_first_sunday, 9, tzinfo=timezone.utc)
            offset = -7 if dst_start <= now < dst_end else -8
            return (now + timedelta(hours=offset)).date()

    def recent_cache_percent(self, provider: str, model: str, limit: int = 10, connection_profile_id: str | None = None):
        rows = [row for row in self.load_history() if row.get("provider") == provider.lower() and self._matches(row.get("model", ""), model)
                and (connection_profile_id is None or self._history_connection_id(row) == connection_profile_id)]
        rows = [row for row in rows if row.get("cache_reported", "cached_input_tokens" in row)][-limit:]
        input_total = sum(int(row.get("input_tokens", 0) or 0) for row in rows)
        cached_total = sum(int(row.get("cached_input_tokens", 0) or 0) for row in rows)
        return round(100 * cached_total / input_total, 1) if input_total else None

    @staticmethod
    def _history_connection_id(row: dict) -> str:
        # Read old histories without rewriting or discarding their records.
        return str(row.get("connection_profile_id") or "legacy")

    def total_cost(self, provider: str | None = None, model: str | None = None, connection_profile_id: str | None = None):
        rows = self.load_history()
        rows = [
            row for row in rows
            if (provider is None or row.get("provider") == provider.lower())
            and (model is None or self._matches(row.get("model", ""), model))
            and (connection_profile_id is None or self._history_connection_id(row) == connection_profile_id)
        ]
        costs = [row.get("cost_usd") for row in rows if row.get("cost_usd") is not None]
        return sum(float(value) for value in costs), len(costs), len(rows)
