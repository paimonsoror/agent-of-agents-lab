"""Distributed-cache domain tools: Valkey via its native protocol (read-only commands)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import valkey.asyncio as valkey

from maestro_common import settings
from maestro_common.events import emit
from maestro_common.llm import ToolSpec

NODE = "valkey"

_SECTIONS = ["memory", "stats", "keyspace", "clients", "server", "persistence", "replication"]
_KEEP = {
    "memory": ("used_memory", "used_memory_human", "used_memory_peak_human", "maxmemory", "maxmemory_human",
               "maxmemory_policy", "mem_fragmentation_ratio", "used_memory_dataset_perc"),
    "stats": ("total_connections_received", "total_commands_processed", "instantaneous_ops_per_sec", "rejected_connections",
              "expired_keys", "evicted_keys", "keyspace_hits", "keyspace_misses", "total_net_input_bytes",
              "total_net_output_bytes"),
    "clients": ("connected_clients", "blocked_clients", "maxclients"),
    "server": ("valkey_version", "redis_version", "uptime_in_seconds", "uptime_in_days"),
}


def _client() -> "valkey.Valkey":
    return valkey.from_url(settings.valkey_url, decode_responses=True, socket_timeout=5)


def _trim(section: str, info: dict[str, Any]) -> dict[str, Any]:
    keep = _KEEP.get(section)
    if not keep:
        return info
    return {k: info[k] for k in keep if k in info}


async def _info(args: dict[str, Any]) -> dict[str, Any]:
    section = args["section"]
    client = _client()
    try:
        info = await client.info(section)
    finally:
        await client.aclose()
    data = _trim(section, info)
    if section == "stats":
        hits, misses = float(info.get("keyspace_hits", 0)), float(info.get("keyspace_misses", 0))
        data["keyspace_hit_ratio_lifetime"] = round(hits / (hits + misses), 4) if hits + misses else None
    emit("evidence.gathered", f"INFO {section}: " + ", ".join(f"{k}={v}" for k, v in list(data.items())[:4]), to=NODE,
         detail={"command": f"INFO {section}", "result": data})
    return data


async def _config(args: dict[str, Any]) -> dict[str, Any]:
    client = _client()
    try:
        cfg = await client.config_get(args["pattern"])
    finally:
        await client.aclose()
    emit("evidence.gathered", f"CONFIG GET {args['pattern']}: {cfg}", to=NODE, detail={"command": f"CONFIG GET {args['pattern']}", "result": cfg})
    return cfg


async def _slowlog(args: dict[str, Any]) -> list[dict[str, Any]]:
    n = max(1, min(int(args["count"]), 50))
    client = _client()
    try:
        entries = await client.slowlog_get(n)
    finally:
        await client.aclose()
    rows = [{"id": e.get("id"), "duration_us": e.get("duration"), "command": " ".join(map(str, e.get("command", [])))[:120]}
            for e in entries]
    emit("evidence.gathered", f"SLOWLOG GET {n}: {len(rows)} entries", to=NODE, detail={"command": f"SLOWLOG GET {n}", "result": rows})
    return rows


async def _keyspace_sample(args: dict[str, Any]) -> dict[str, Any]:
    limit = max(50, min(int(args.get("count", 500)), 2000))
    client = _client()
    try:
        total = await client.dbsize()
        prefixes: Counter[str] = Counter()
        cursor, seen = 0, 0
        while seen < limit:
            cursor, keys = await client.scan(cursor=cursor, count=200)
            for k in keys:
                prefixes[str(k).split(":", 1)[0]] += 1
            seen += len(keys)
            if cursor == 0:
                break
    finally:
        await client.aclose()
    sample = {"dbsize": total, "sampled": seen, "prefix_counts": dict(prefixes.most_common(10))}
    emit("evidence.gathered", f"Keyspace: {total} keys; top prefixes {dict(prefixes.most_common(3))}", to=NODE, detail=sample)
    return sample


def build_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="valkey_info",
            description="Run INFO <section> on the Valkey cache and return the fields that matter (memory, stats incl. evictions and hit ratio, keyspace, clients, server).",
            input_schema={"type": "object", "properties": {"section": {"type": "string", "enum": _SECTIONS, "description": "INFO section"}}},
            handler=_info,
        ),
        ToolSpec(
            name="valkey_config",
            description="CONFIG GET <pattern>, e.g. maxmemory* to see the memory ceiling and eviction policy.",
            input_schema={"type": "object", "properties": {"pattern": {"type": "string", "description": "Glob pattern such as maxmemory*"}}},
            handler=_config,
        ),
        ToolSpec(
            name="valkey_slowlog",
            description="Return the most recent slow commands (SLOWLOG GET n).",
            input_schema={"type": "object", "properties": {"count": {"type": "integer", "description": "How many entries, 1-50"}}},
            handler=_slowlog,
        ),
        ToolSpec(
            name="valkey_sample_keys",
            description="DBSIZE plus a SCAN sample grouped by key prefix, to see which application (or filler) owns the keyspace.",
            input_schema={"type": "object", "properties": {"count": {"type": "integer", "description": "Sample size, 50-2000"}}},
            handler=_keyspace_sample,
        ),
    ]


async def health() -> dict[str, Any]:
    client = _client()
    try:
        pong = await client.ping()
        info = await client.info("memory")
    finally:
        await client.aclose()
    return {"status": "ok" if pong else "degraded", "used_memory_human": info.get("used_memory_human"),
            "maxmemory_human": info.get("maxmemory_human")}
