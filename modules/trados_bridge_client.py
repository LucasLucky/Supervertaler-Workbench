"""
Trados Bridge Client
====================

Client for the Sidekick Bridge (a localhost HTTP API exposed by the
Supervertaler for Trados plugin – see Core/SidekickBridge.cs in that repo).

Discovery flow:
  1. Resolve the shared user-data root (same `%APPDATA%\\Supervertaler\\config.json`
     pointer that llm_clients.load_api_keys() reads).
  2. Look for the handshake file at  <root>/trados/runtime/bridge.json
     written by the plugin while it's running.  Contains:
         {version, port, token, pid, startedAt}
  3. Cache the handshake until the file's mtime changes.

Liveness:
  We don't bother with PID liveness checks – on every call we just attempt
  the HTTP request with a short timeout.  Connection refused / timeout is
  fast on localhost (~1 ms) and is the only reliable signal; a stale
  handshake file from a hard kill simply produces a clean failure.

API:
  client.is_available()                        -> bool   (cheap network check)
  client.fetch_active_context()                -> dict | None
  client.insert_translation(text: str)         -> (ok: bool, error: str | None)

All methods are synchronous and safe to call from a Qt UI thread because
they always use very short HTTP timeouts (default 1.5 s).  Callers who
need fully async behaviour should drive this from a worker thread.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

try:
    import requests
except ImportError:  # pragma: no cover – Workbench already depends on requests
    requests = None  # type: ignore


# ── Path resolution ────────────────────────────────────────────────────────


def _resolve_user_data_root() -> Path:
    """
    Mirror the resolution rules used by ``llm_clients.load_api_keys`` so this
    client always looks where the plugin is actually writing.  Falls back to
    ``~/Supervertaler`` when no pointer file exists.
    """
    # Pointer file location is OS-specific
    if sys.platform == "win32":
        pointer = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "Supervertaler" / "config.json"
    elif sys.platform == "darwin":
        pointer = Path.home() / "Library" / "Application Support" / "Supervertaler" / "config.json"
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        pointer = xdg / "Supervertaler" / "config.json"

    if pointer.exists():
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
            configured = data.get("user_data_path")
            if configured:
                return Path(configured)
        except Exception:
            pass

    return Path.home() / "Supervertaler"


def _bridge_handshake_path() -> Path:
    """Absolute path to the handshake file the plugin writes."""
    return _resolve_user_data_root() / "trados" / "runtime" / "bridge.json"


# ── Client ─────────────────────────────────────────────────────────────────


class TradosBridgeClient:
    """
    Singleton-friendly client.  One instance per Sidekick is fine; the
    handshake parse is cheap (cached against mtime) and there's no per-instance
    network state to leak.
    """

    # How long to cache "no handshake file present" before re-checking the
    # disk.  Keeps `is_available` cheap when the user is rapidly typing.
    _MISSING_HANDSHAKE_TTL_S = 1.0

    # HTTP timeouts.  Localhost is fast; if these are hit, the bridge is sick.
    _HTTP_TIMEOUT_AVAILABILITY = 0.5
    _HTTP_TIMEOUT_GET_CONTEXT = 1.5
    _HTTP_TIMEOUT_INSERT = 2.0

    def __init__(self) -> None:
        self._handshake: Optional[Dict[str, Any]] = None
        self._handshake_mtime: float = 0.0
        self._last_missing_check: float = 0.0

    # ── Discovery ─────────────────────────────────────────────────────

    def _load_handshake(self) -> Optional[Dict[str, Any]]:
        """
        Returns the parsed handshake dict, or None if no usable handshake
        is on disk.  Caches the parsed value against the file's mtime so
        repeated calls during typing don't re-parse the file.
        """
        path = _bridge_handshake_path()

        try:
            stat = path.stat()
        except FileNotFoundError:
            # Cache "no file" for a short window so polling stays cheap.
            now = time.monotonic()
            if now - self._last_missing_check < self._MISSING_HANDSHAKE_TTL_S:
                return None
            self._last_missing_check = now
            self._handshake = None
            self._handshake_mtime = 0.0
            return None
        except OSError:
            return None

        if self._handshake is not None and stat.st_mtime == self._handshake_mtime:
            return self._handshake

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._handshake = None
            self._handshake_mtime = 0.0
            return None

        # Schema sanity check – ignore handshakes from a future protocol
        # version we don't understand.
        if not isinstance(data, dict) or data.get("version") != 1:
            self._handshake = None
            self._handshake_mtime = 0.0
            return None
        if not data.get("port") or not data.get("token"):
            self._handshake = None
            self._handshake_mtime = 0.0
            return None

        self._handshake = data
        self._handshake_mtime = stat.st_mtime
        return data

    # ── Availability ──────────────────────────────────────────────────

    def is_available(self) -> bool:
        """
        Returns True when (a) a valid handshake file is on disk and (b) the
        listener responds to a tiny request.  Connection-refused on localhost
        is fast; a stale handshake from a hard kill therefore degrades to a
        clean False without hanging the UI.
        """
        if requests is None:
            return False
        hs = self._load_handshake()
        if hs is None:
            return False

        # Use a no-route GET as a cheap liveness probe – the bridge will
        # respond with 404 (= alive but path unknown) or 401 (= alive but
        # auth missing).  Either is fine for "is it up?".
        url = f"http://127.0.0.1:{hs['port']}/_ping"
        try:
            r = requests.get(url, timeout=self._HTTP_TIMEOUT_AVAILABILITY)
            # Any HTTP response (including 401/404) means the bridge is alive.
            return r.status_code != 0
        except Exception:
            # Connection refused, timeout, etc. – bridge not reachable.
            # Drop the cached handshake so a fresh start is detected on the
            # next poll without waiting for the mtime cache to expire.
            self._handshake = None
            self._handshake_mtime = 0.0
            return False

    # ── Endpoints ─────────────────────────────────────────────────────

    def fetch_active_context(self) -> Optional[Dict[str, Any]]:
        """
        GET /v1/active-context.  Returns the JSON body as a dict, or None
        if the bridge isn't reachable / didn't respond cleanly.
        """
        if requests is None:
            return None
        hs = self._load_handshake()
        if hs is None:
            return None
        url = f"http://127.0.0.1:{hs['port']}/v1/active-context"
        headers = {"Authorization": f"Bearer {hs['token']}"}
        try:
            r = requests.get(url, headers=headers, timeout=self._HTTP_TIMEOUT_GET_CONTEXT)
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            return None

    def insert_translation(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        POST /v1/insert-translation.  Returns (ok, error_message_or_None).
        """
        if requests is None:
            return False, "Python `requests` library not installed"
        if not text:
            return False, "empty text"
        hs = self._load_handshake()
        if hs is None:
            return False, "Trados plugin not detected (no handshake file)"
        url = f"http://127.0.0.1:{hs['port']}/v1/insert-translation"
        headers = {
            "Authorization": f"Bearer {hs['token']}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            r = requests.post(url, headers=headers, data=json.dumps({"text": text}).encode("utf-8"),
                              timeout=self._HTTP_TIMEOUT_INSERT)
            if r.status_code == 200:
                return True, None
            try:
                body = r.json()
                err = body.get("error") or f"HTTP {r.status_code}"
            except Exception:
                err = f"HTTP {r.status_code}"
            return False, err
        except Exception as e:
            return False, str(e)


# ── Prompt formatting ──────────────────────────────────────────────────────


def format_context_for_prompt(ctx: Dict[str, Any]) -> str:
    """
    Convert a `/v1/active-context` snapshot into a plain-text block suitable
    for prepending to the chat system prompt.  Mirrors the shape of the
    in-Trados ChatPrompt builder so answer quality is comparable.

    Returns "" if the snapshot indicates no active document or no usable
    context.
    """
    if not isinstance(ctx, dict) or not ctx.get("available"):
        return ""

    lines = []
    lines.append("# TRADOS PROJECT CONTEXT")
    lines.append("The user is currently translating in Trados Studio. The following context "
                 "describes the active project and segment. Use this to ground your answer "
                 "in the user's real work.")
    lines.append("")

    project = ctx.get("project") or {}
    if project:
        lines.append("## Project")
        if project.get("name"):
            lines.append(f"- Name: {project['name']}")
        if project.get("fileName"):
            lines.append(f"- File: {project['fileName']}")
        src = project.get("sourceLang")
        tgt = project.get("targetLang")
        if src and tgt:
            lines.append(f"- Language pair: {src} → {tgt}")
        elif src:
            lines.append(f"- Source language: {src}")
        elif tgt:
            lines.append(f"- Target language: {tgt}")
        lines.append("")

    seg = ctx.get("activeSegment") or {}
    if seg:
        lines.append("## Active segment")
        if seg.get("source"):
            lines.append(f"- Source: {seg['source']}")
        if seg.get("target"):
            lines.append(f"- Current target draft: {seg['target']}")
        else:
            lines.append("- Current target draft: (empty)")
        lines.append("")

    surrounding = ctx.get("surroundingSegments") or []
    if surrounding:
        lines.append("## Surrounding segments (immediate context)")
        for s in surrounding:
            src = s.get("source") or ""
            tgt = s.get("target") or ""
            if tgt:
                lines.append(f"- {src}  →  {tgt}")
            else:
                lines.append(f"- {src}  →  (untranslated)")
        lines.append("")

    tm_matches = ctx.get("tmMatches") or []
    if tm_matches:
        lines.append("## Translation Memory matches for the active segment")
        for m in tm_matches:
            score = m.get("score")
            src = m.get("source") or ""
            tgt = m.get("target") or ""
            tm_name = m.get("tmName")
            label = f"{score}%" if score is not None else "?"
            suffix = f"  [{tm_name}]" if tm_name else ""
            lines.append(f"- ({label}) {src}  →  {tgt}{suffix}")
        lines.append("")

    termbase_hits = ctx.get("termbaseHits") or []
    if termbase_hits:
        lines.append("## Termbase hits for the active segment")
        for t in termbase_hits:
            src = t.get("source") or ""
            tgt = t.get("target") or ""
            tb = t.get("termbaseName")
            extra = []
            if t.get("definition"):
                extra.append(f"def: {t['definition']}")
            if t.get("domain"):
                extra.append(f"domain: {t['domain']}")
            if t.get("notes"):
                extra.append(f"notes: {t['notes']}")
            tb_suffix = f"  [{tb}]" if tb else ""
            extras = f"  ({'; '.join(extra)})" if extra else ""
            lines.append(f"- {src}  →  {tgt}{tb_suffix}{extras}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
