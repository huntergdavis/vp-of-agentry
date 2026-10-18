"""Owner-only LAN dashboard for existing Herdr agents.

The web process stores owner messages through Dunking Sheep's durable inbox.
Herdr pane output is a live view, not a structured transcript; authored briefs
are stored in SQLite.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("VP_DATA_DIR", ROOT / "data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS = DATA / "uploads"
UPLOADS.mkdir(exist_ok=True)
DB = DATA / "messages.sqlite3"
AUTH = DATA / "auth.json"
CREDENTIALS = DATA / "owner-credentials"
CODEWHEEL_DIR = Path(os.getenv("VP_CODEWHEEL_DIR", DATA / "codewheel")).resolve()
DUNKING_SHEEP = Path(os.getenv("DUNKING_SHEEP_DIR", ROOT.parent / "dunkingsheep"))
DASHBOARD_DIR = Path(os.getenv("POOLRAD_DASHBOARD_DIR", ROOT / "integrations" / "poolrad-dashboard")).resolve()
DASHBOARD_REPO = Path(os.getenv("POOLRAD_DASHBOARD_REPO", ROOT.parent / "poolrad-decomp-opencode-ds41flash")).resolve()
DASHBOARD_REPORTS = {"SLOT_A_FIRST_EGA_ROW64.md", "SLOT_A_ROW6_COL38_PRINTER_PAGE.md"}
sys.path.insert(0, str(DUNKING_SHEEP))

def _load_channels():
    override = os.getenv("VP_CHANNELS_FILE")
    path = Path(override).expanduser() if override else ROOT / "channels.json"
    if not path.exists():
        if override:
            raise FileNotFoundError(f"VP_CHANNELS_FILE does not exist: {path}")
        path = ROOT / "channels.example.json"
    payload = json.loads(path.read_text())
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"{path}: expected a nonempty list of channels")
    ids = set()
    for item in payload:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str) and item[key].strip()
            for key in ("id", "name", "match", "kind")
        ):
            raise ValueError(f"{path}: each channel needs nonempty id, name, match, and kind")
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", item["id"]):
            raise ValueError(f"{path}: invalid channel id {item['id']!r}")
        if item["kind"] not in {"active", "standby", "monitor"}:
            raise ValueError(f"{path}: invalid kind for channel {item['id']!r}")
        if item["id"] in ids:
            raise ValueError(f"{path}: duplicate channel id {item['id']!r}")
        if "dashboard" in item and not isinstance(item["dashboard"], bool):
            raise ValueError(f"{path}: dashboard must be true or false")
        ids.add(item["id"])
    return payload


CHANNELS = _load_channels()
CHANNEL_INDEX = {item["id"]: item for item in CHANNELS}
from server.roster import build_roster, discovered_id, match_pane, presence
from server.gameplay import GameError, GameSession
GAME = GameSession(Path(os.getenv("POOLRAD_REPO_DIR", ROOT.parent / "poolrad-decomp")).resolve(), DATA)
MAX_UPLOAD = 25 * 1024 * 1024
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
DELIVERY_LOCK = threading.Lock()
DELIVERY_STOP = threading.Event()
READ_STATUS_WINDOW_S = 8 * 24 * 3600  # Inbox retains read messages for seven days.
PANES_ACTIVITY_TTL_S = 4
PANES_ACTIVITY_LOCK = threading.Lock()
PANES_ACTIVITY_CACHE = {"expires": 0.0, "data": None}


@contextmanager
def _db():
    conn = sqlite3.connect(DB, timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn
    finally:
        conn.close()


def _initialize():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                role TEXT NOT NULL,
                body TEXT NOT NULL,
                delivery TEXT NOT NULL DEFAULT 'posted',
                delivery_detail TEXT NOT NULL DEFAULT '',
                transport_id TEXT,
                transport_attempts INTEGER NOT NULL DEFAULT 0,
                transport_attempt_at REAL NOT NULL DEFAULT 0,
                external_id TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS messages_channel_id ON messages(channel,id);
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                mime TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                message_id INTEGER REFERENCES messages(id),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS attachments_message_id ON attachments(message_id);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                expires_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_expires_at ON sessions(expires_at);
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        if "transport_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN transport_id TEXT")
        if "delivery_detail" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN delivery_detail TEXT NOT NULL DEFAULT ''")
        if "transport_attempts" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN transport_attempts INTEGER NOT NULL DEFAULT 0")
        if "transport_attempt_at" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN transport_attempt_at REAL NOT NULL DEFAULT 0")
        if "external_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN external_id TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS messages_external_id ON messages(channel,external_id) WHERE external_id IS NOT NULL")
    if not AUTH.exists():
        password = os.getenv("VP_PASSWORD") or secrets.token_urlsafe(18)
        token = secrets.token_urlsafe(32)
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 400_000)
        AUTH.write_text(json.dumps({"salt": salt.hex(), "digest": digest.hex(), "token": token}))
        AUTH.chmod(0o600)
        CREDENTIALS.write_text(f"Password: {password}\nAPI token: {token}\n")
        CREDENTIALS.chmod(0o600)


_initialize()
app = FastAPI(title="VP of Agentry", docs_url=None, redoc_url=None)


def _auth_record():
    return json.loads(AUTH.read_text())


def _password_matches(password: str, record: dict):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(record["salt"]), 400_000)
    return hmac.compare_digest(digest, bytes.fromhex(record["digest"]))


def _private_write(path: Path, content: str):
    """Replace a credential file atomically without exposing its contents in Git."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sync_edited_credentials():
    """Honor a local owner's edited Password line on the next login."""
    if not CREDENTIALS.exists() or CREDENTIALS.stat().st_mtime_ns <= AUTH.stat().st_mtime_ns:
        return
    match = re.search(r"^Password: (.+)$", CREDENTIALS.read_text(), re.MULTILINE)
    if not match:
        return
    password = match.group(1)
    record = _auth_record()
    if _password_matches(password, record):
        return
    salt = secrets.token_bytes(16)
    record["salt"] = salt.hex()
    record["digest"] = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 400_000).hex()
    _private_write(AUTH, json.dumps(record))
    with _db() as conn:
        conn.execute("DELETE FROM sessions")


def _session_key(cookie: str) -> str:
    return hashlib.sha256(cookie.encode()).hexdigest()


def _same_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        raise HTTPException(403, "Cross-origin request refused")


def require_auth(request: Request):
    _same_origin(request)
    bearer = request.headers.get("authorization", "")
    if bearer.startswith("Bearer ") and hmac.compare_digest(bearer[7:], _auth_record()["token"]):
        return "api"
    cookie = request.cookies.get("vp_session", "")
    if cookie:
        with _db() as conn:
            row = conn.execute("SELECT expires_at FROM sessions WHERE token_hash=?", (_session_key(cookie),)).fetchone()
            if row and row["expires_at"] > time.time():
                return "owner"
            if row:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (_session_key(cookie),))
    raise HTTPException(401, "Sign in required")


class Login(BaseModel):
    password: str


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    _same_origin(request)
    _sync_edited_credentials()
    addr = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = [t for t in LOGIN_ATTEMPTS.get(addr, []) if now - t < 300]
    if len(attempts) >= 8:
        raise HTTPException(429, "Too many attempts; retry in five minutes")
    record = _auth_record()
    if not _password_matches(body.password, record):
        LOGIN_ATTEMPTS[addr] = attempts + [now]
        raise HTTPException(401, "Incorrect password")
    LOGIN_ATTEMPTS.pop(addr, None)
    session = secrets.token_urlsafe(32)
    with _db() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
        conn.execute("INSERT INTO sessions(token_hash,expires_at) VALUES(?,?)", (_session_key(session), now + 7 * 24 * 3600))
    response.set_cookie("vp_session", session, httponly=True, samesite="strict", max_age=7 * 24 * 3600)
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request, response: Response, _: Annotated[str, Depends(require_auth)]):
    cookie = request.cookies.get("vp_session", "")
    if cookie:
        with _db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_session_key(cookie),))
    response.delete_cookie("vp_session")
    return {"ok": True}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


@app.post("/api/password")
def change_password(body: PasswordChange, request: Request, identity: Annotated[str, Depends(require_auth)]):
    if identity != "owner":
        raise HTTPException(403, "Owner sign-in required")
    record = _auth_record()
    if not _password_matches(body.current_password, record):
        raise HTTPException(403, "Current password is incorrect")
    salt = secrets.token_bytes(16)
    record["salt"] = salt.hex()
    record["digest"] = hashlib.pbkdf2_hmac("sha256", body.new_password.encode(), salt, 400_000).hex()
    _private_write(AUTH, json.dumps(record))
    if CREDENTIALS.exists():
        _private_write(CREDENTIALS, f"Password: {body.new_password}\nAPI token: {record['token']}\n")
    current = request.cookies.get("vp_session", "")
    with _db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash<>?", (_session_key(current),))
    return {"ok": True}


def _flock():
    try:
        from dunk_client import FlockClient
        return FlockClient.connect_or_start()
    except Exception as exc:
        raise HTTPException(503, f"Dunking Sheep unavailable: {exc}") from exc


def _panes():
    return _flock().call("list_panes")["panes"]


def _target(channel: str, panes: list[dict]):
    cfg = CHANNEL_INDEX.get(channel)
    if cfg:
        return match_pane(cfg, panes)
    for pane in panes:
        if pane.get("agent") and discovered_id(pane.get("pane_id", "")) == channel:
            return pane
    if _known_channel(channel):
        return None
    raise HTTPException(404, "Unknown channel")


def _presence(raw_status: str | None):
    # Herdr's "blocked" can mean a transient tool wait. It is not evidence of
    # a project blocker or a decision needed from the owner.
    return presence(raw_status)


def _known_channel(channel: str) -> bool:
    return channel in CHANNEL_INDEX or bool(re.fullmatch(r"pane-[a-z0-9-]+", channel))


@app.get("/api/channels")
def channels(_: Annotated[str, Depends(require_auth)]):
    try:
        panes = _panes()
        daemon = True
    except HTTPException:
        panes, daemon = [], False
    rows = build_roster(CHANNELS, panes)
    return {"channels": rows, "daemon": daemon,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


@app.get("/api/ops-metrics")
def operations_metrics(_: Annotated[str, Depends(require_auth)]):
    from ops_metrics import connect, summary

    try:
        conn = connect()
        try:
            return summary(conn)
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, f"Operations metrics unavailable: {type(exc).__name__}") from exc


@app.get("/api/ops-metrics/history")
def operations_metrics_history(_: Annotated[str, Depends(require_auth)], hours: int = 24):
    from ops_metrics import connect, history

    if not 1 <= hours <= 168:
        raise HTTPException(422, "History window must be 1 to 168 hours")

    try:
        conn = connect()
        try:
            return history(conn, hours=hours)
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, f"Operations metrics history unavailable: {type(exc).__name__}") from exc


@app.post("/api/ops-metrics/refresh")
def refresh_operations_metrics(_: Annotated[str, Depends(require_auth)]):
    from ops_metrics import collect, connect

    try:
        conn = connect()
        try:
            return collect(conn, force_external=True)
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, f"Operations metrics unavailable: {type(exc).__name__}") from exc


def _message(row, conn):
    item = dict(row)
    item["attachments"] = [dict(r) for r in conn.execute(
        "SELECT id,filename,mime,size FROM attachments WHERE message_id=? ORDER BY created_at", (row["id"],))]
    return item


def _prompt_for(row, conn):
    attachments = conn.execute("SELECT filename,path FROM attachments WHERE message_id=? ORDER BY created_at", (row["id"],)).fetchall()
    references = "\n".join(f"- {item['filename']}: {item['path']}" for item in attachments)
    prompt = row["body"].strip()
    if references:
        prompt += f"\n\nAttached files on this host (read these paths directly):\n{references}"
    return prompt + f"\n\n[VP web message #{row['id']}; reply through vpctl brief --channel {row['channel']} when a concise response is ready.]"


def _send_saved(row, client, pane, force=False):
    with _db() as conn:
        prompt = _prompt_for(row, conn)
        attachments = [item["path"] for item in conn.execute(
            "SELECT path FROM attachments WHERE message_id=? ORDER BY created_at", (row["id"],))]
    # A generic model-name mailbox can be shared by unrelated panes. Until
    # Dunking Sheep gives such panes stable unique keys, address them by pane.
    mailbox = "" if force else str(client.call("inbox_count", mailbox=pane["pane_id"]).get("mailbox") or "")
    use_inbox = bool(mailbox) and mailbox.casefold() not in {"codex", "claude", "opencode"}
    if not use_inbox:
        result = client.call("send_text", target=pane["pane_id"], text=prompt,
                             hold_while_typing=not force, wait_s=0)
        delivery = "queued" if result.get("queued") else "sent" if result.get("ok") else "uncertain"
        detail = result.get("message", "")
    else:
        result = client.call("inbox_send", to=pane["pane_id"], body=prompt,
                             subject=f"VP web message #{row['id']}", attach=attachments, notify=True)
        if not result.get("message_id", "").startswith("i"):
            raise RuntimeError("Inbox send returned no message ID")
        delivery = {"queued": "inbox", "read": "read", "acked": "acked"}.get(result.get("state"), "uncertain")
        detail = {"inbox": "Stored in agent inbox", "read": "Read by agent", "acked": "Handled by agent"}.get(delivery, "Inbox state unconfirmed")
    with _db() as conn:
        conn.execute("UPDATE messages SET delivery=?,delivery_detail=?,transport_id=?,"
                     "transport_attempts=transport_attempts+1,transport_attempt_at=? WHERE id=?",
                     (delivery, detail, result.get("message_id"), time.time(), row["id"]))
    return result


def _reconcile(channel: str):
    """Read transport state; never replay an ambiguous attempt automatically."""
    if not DELIVERY_LOCK.acquire(blocking=False):
        return
    try:
        read_cutoff = time.time() - READ_STATUS_WINDOW_S
        with _db() as conn:
            queued = conn.execute("SELECT * FROM messages WHERE channel=? AND "
                                  "(delivery IN ('pending','queued','failed','uncertain','inbox') "
                                  "OR (delivery='read' AND transport_attempt_at>?)) ORDER BY id",
                                  (channel, read_cutoff)).fetchall()
        if not queued:
            return
        client = _flock()
        legacy = [row for row in queued if not (row["transport_id"] or "").startswith("i")]
        recent = client.call("list_messages") if legacy else {"queued": [], "recent": []}
        queued_by_id = {item.get("message_id"): item for item in recent.get("queued", [])}
        for row in queued:
            record = None
            transport_id = row["transport_id"]
            if transport_id and transport_id.startswith("i"):
                try:
                    inbox_record = client.call("inbox_status", message_id=transport_id)
                    state = inbox_record.get("state")
                except Exception:
                    continue  # Retain the last known state through a daemon outage.
                delivery = {"queued": "inbox", "read": "read", "acked": "acked", "cancelled": "cancelled"}.get(state)
                if delivery:
                    detail = {"inbox": "Stored in agent inbox", "read": "Read by agent",
                              "acked": "Handled by agent", "cancelled": "Cancelled"}[delivery]
                    if delivery == "inbox":
                        notify_state = (inbox_record.get("notify") or {}).get("state")
                        if notify_state == "queued":
                            detail += "; wakeup waiting for agent input to clear"
                        elif notify_state == "failed":
                            detail += "; wakeup failed"
                        elif notify_state == "sent":
                            detail += "; agent notified"
                    with _db() as conn:
                        conn.execute("UPDATE messages SET delivery=?,delivery_detail=? WHERE id=?",
                                     (delivery, detail, row["id"]))
                continue
            if transport_id:
                try:
                    record = client.call("get_message", message_id=transport_id)
                except Exception as exc:
                    if "no message with id" not in str(exc):
                        continue
            if record is None:
                matches = [item for item in recent.get("queued", []) + recent.get("recent", [])
                           if f"[VP web message #{row['id']};" in item.get("text", "")]
                if matches:
                    record = next((item for item in matches if item.get("status") == "sent"), matches[0])
                    transport_id = record.get("message_id")
            if record:
                state = record.get("status")
                if state in {"queued", "sent", "cancelled"}:
                    detail = record.get("message", "")
                    if state == "queued":
                        blocker = queued_by_id.get(transport_id, {}).get("blocked_by")
                        if blocker:
                            detail = f"Waiting: {blocker}"
                    with _db() as conn:
                        conn.execute("UPDATE messages SET delivery=?,delivery_detail=?,transport_id=? WHERE id=?",
                                     (state, detail, transport_id, row["id"]))
                    continue
            # A failed or vanished in-memory entry may actually have been
            # submitted before the daemon timed out. Keep its original ID and
            # let the owner inspect the pane; automatic replay caused duplicates.
            with _db() as conn:
                conn.execute("UPDATE messages SET delivery='uncertain',delivery_detail=? WHERE id=?",
                             ("Delivery unconfirmed. Check agent activity before sending again.", row["id"]))
    except Exception:
        # A daemon outage never discards the durable owner message.
        return
    finally:
        DELIVERY_LOCK.release()


def _delivery_watch():
    while not DELIVERY_STOP.wait(5):
        try:
            with _db() as conn:
                channels = [row[0] for row in conn.execute(
                    "SELECT DISTINCT channel FROM messages WHERE delivery IN "
                    "('pending','queued','failed','uncertain','inbox') "
                    "OR (delivery='read' AND transport_attempt_at>?)",
                    (time.time() - READ_STATUS_WINDOW_S,))]
            for channel in channels:
                _reconcile(channel)
        except Exception:
            pass


@app.on_event("startup")
def start_delivery_watch():
    GAME.recover_orphans()
    DELIVERY_STOP.clear()
    app.state.delivery_thread = threading.Thread(target=_delivery_watch, name="vp-delivery-watch", daemon=True)
    app.state.delivery_thread.start()


@app.on_event("shutdown")
def stop_delivery_watch():
    DELIVERY_STOP.set()
    app.state.delivery_thread.join(timeout=6)
    GAME.stop()


class GameStart(BaseModel):
    fresh: bool = False


class GameKey(BaseModel):
    key: str = Field(min_length=1, max_length=16)


class GameType(BaseModel):
    text: str = Field(min_length=1, max_length=64)
    submit: bool = True


@app.get("/api/game/status")
def game_status(_: Annotated[str, Depends(require_auth)]):
    return GAME.status()


@app.get("/api/game/codewheel/{filename}")
def game_codewheel_image(filename: str, _: Annotated[str, Depends(require_auth)]):
    if not re.fullmatch(r"(?:esp|det)(?:0[1-9]|[12][0-9]|3[0-6])\.gif", filename):
        raise HTTPException(404, "Unknown rune template")
    path = CODEWHEEL_DIR / filename
    if path.is_symlink() or not path.is_file():
        raise HTTPException(404, "Private rune template unavailable")
    return FileResponse(path, media_type="image/gif", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
    })


@app.post("/api/game/start")
def game_start(body: GameStart, _: Annotated[str, Depends(require_auth)]):
    try:
        return GAME.start(body.fresh)
    except GameError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/game/stop")
def game_stop(_: Annotated[str, Depends(require_auth)]):
    return GAME.stop()


@app.post("/api/game/key")
def game_key(body: GameKey, _: Annotated[str, Depends(require_auth)]):
    try:
        GAME.key(body.key)
    except GameError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.post("/api/game/type")
def game_type(body: GameType, _: Annotated[str, Depends(require_auth)]):
    try:
        GAME.type_text(body.text, body.submit)
    except GameError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.get("/api/game/video")
def game_video(_: Annotated[str, Depends(require_auth)]):
    if not GAME.status()["running"]:
        raise HTTPException(404, "Poolrad is not running")
    return StreamingResponse(GAME.stream("video"), media_type="multipart/x-mixed-replace;boundary=ffmpeg",
                             headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.get("/api/game/audio")
def game_audio(_: Annotated[str, Depends(require_auth)]):
    status = GAME.status()
    if not status["running"] or not status["audio"]:
        raise HTTPException(404, "Poolrad audio is unavailable")
    return StreamingResponse(GAME.stream("audio"), media_type="audio/ogg", headers={"Cache-Control": "no-store"})


@app.get("/api/messages")
def messages(channel: str, _: Annotated[str, Depends(require_auth)], before: int | None = None, limit: int = 50):
    if not _known_channel(channel):
        raise HTTPException(404, "Unknown channel")
    _reconcile(channel)
    limit = max(1, min(limit, 100))
    with _db() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE channel=? AND id<? ORDER BY id DESC LIMIT ?",
                            (channel, before or 2**63 - 1, limit + 1)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        return {"items": [_message(r, conn) for r in reversed(rows)], "has_more": more,
                "next_before": rows[-1]["id"] if rows else None}


@app.get("/api/deliveries")
def deliveries(channel: str, ids: str, _: Annotated[str, Depends(require_auth)]):
    if not _known_channel(channel):
        raise HTTPException(404, "Unknown channel")
    try:
        message_ids = [int(part) for part in ids.split(",") if part]
    except ValueError:
        raise HTTPException(422, "Invalid message IDs")
    if len(message_ids) > 100 or any(item < 1 for item in message_ids):
        raise HTTPException(422, "Too many or invalid message IDs")
    _reconcile(channel)
    if not message_ids:
        return {"deliveries": {}}
    placeholders = ",".join("?" for _ in message_ids)
    with _db() as conn:
        rows = conn.execute(f"SELECT id,delivery,delivery_detail FROM messages WHERE channel=? AND id IN ({placeholders})",
                            [channel, *message_ids]).fetchall()
    return {"deliveries": {str(row["id"]): {"delivery": row["delivery"], "delivery_detail": row["delivery_detail"]} for row in rows}}


@app.get("/api/messages/{message_id}/context")
def message_context(message_id: int, _: Annotated[str, Depends(require_auth)]):
    with _db() as conn:
        anchor = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if not anchor:
            raise HTTPException(404, "Message not found")
        channel = anchor["channel"]
    _reconcile(channel)
    with _db() as conn:
        anchor = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        earlier = conn.execute("SELECT * FROM messages WHERE channel=? AND id<? ORDER BY id DESC LIMIT 25",
                               (channel, message_id)).fetchall()
        later = conn.execute("SELECT * FROM messages WHERE channel=? AND id>? ORDER BY id ASC LIMIT 25",
                             (channel, message_id)).fetchall()
        rows = list(reversed(earlier)) + [anchor] + later
        has_older = conn.execute("SELECT 1 FROM messages WHERE channel=? AND id<? LIMIT 1",
                                 (channel, rows[0]["id"])).fetchone() is not None
        return {"channel": channel, "items": [_message(row, conn) for row in rows],
                "has_more": has_older, "next_before": rows[0]["id"]}


class MessageIn(BaseModel):
    channel: str
    body: str = Field(default="", max_length=12000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    external_id: str | None = Field(default=None, max_length=100)


@app.post("/api/messages")
def post_message(data: MessageIn, identity: Annotated[str, Depends(require_auth)]):
    if not _known_channel(data.channel):
        raise HTTPException(404, "Unknown channel")
    if not data.body.strip() and not data.attachment_ids:
        raise HTTPException(422, "Message is empty")
    if data.external_id:
        with _db() as conn:
            existing = conn.execute("SELECT * FROM messages WHERE channel=? AND external_id=?",
                                    (data.channel, data.external_id)).fetchone()
            if existing:
                return _message(existing, conn)
    pane = _target(data.channel, _panes())
    if not pane or not pane.get("agent"):
        raise HTTPException(409, "No active agent is available in this channel")
    with _db() as conn:
        if data.external_id:
            existing = conn.execute("SELECT * FROM messages WHERE channel=? AND external_id=?",
                                    (data.channel, data.external_id)).fetchone()
            if existing:
                return _message(existing, conn)
        attachment_rows = []
        for attachment_id in data.attachment_ids:
            row = conn.execute("SELECT * FROM attachments WHERE id=? AND message_id IS NULL", (attachment_id,)).fetchone()
            if not row:
                raise HTTPException(422, f"Attachment {attachment_id} is unavailable")
            attachment_rows.append(row)
        cursor = conn.execute("INSERT INTO messages(channel,role,body,delivery,transport_attempt_at,external_id) VALUES(?,?,?,?,?,?)",
                              (data.channel, "owner", data.body.strip(), "pending", time.time(), data.external_id))
        message_id = cursor.lastrowid
        for row in attachment_rows:
            conn.execute("UPDATE attachments SET message_id=? WHERE id=?", (message_id, row["id"]))
        row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
    try:
        result = _send_saved(row, _flock(), pane)
    except Exception as exc:
        result = {"error": str(exc)}
        with _db() as conn:
            conn.execute("UPDATE messages SET delivery='uncertain',delivery_detail=?,transport_attempts=transport_attempts+1,transport_attempt_at=? WHERE id=?",
                         ("Delivery unconfirmed. Check agent activity before sending again.", time.time(), message_id))
    with _db() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        item = _message(row, conn)
    item["transport"] = result
    return item


@app.post("/api/messages/{message_id}/send-now")
def send_now(message_id: int, identity: Annotated[str, Depends(require_auth)]):
    if identity != "owner":
        raise HTTPException(403, "Owner sign-in required")
    with DELIVERY_LOCK:
        with _db() as conn:
            row = conn.execute("SELECT * FROM messages WHERE id=? AND role='owner'", (message_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Message not found")
        if row["delivery"] == "sent":
            with _db() as conn:
                return _message(row, conn)
        if row["delivery"] not in {"queued", "pending"} or not row["transport_id"]:
            raise HTTPException(409, "Message is being recovered; try again shortly")
        client = _flock()
        try:
            record = client.call("get_message", message_id=row["transport_id"])
        except Exception:
            raise HTTPException(409, "Transport state unavailable; try again shortly")
        if record.get("status") == "sent":
            with _db() as conn:
                conn.execute("UPDATE messages SET delivery='sent',delivery_detail='sent' WHERE id=?", (message_id,))
                return _message(conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone(), conn)
        if record.get("status") != "queued":
            raise HTTPException(409, "Message is no longer queued; refresh its status")
        queued = client.call("list_messages").get("queued", [])
        blocked = next((item.get("blocked_by") for item in queued
                        if item.get("message_id") == row["transport_id"]), None)
        if "someone is typing" not in record.get("message", "") and blocked != "input box contains a draft":
            raise HTTPException(409, "This message is queued for transport, not held behind a draft")
        try:
            client.call("cancel_message", message_id=row["transport_id"])
        except Exception:
            # The worker may have sent it between inspection and cancellation.
            latest = client.call("get_message", message_id=row["transport_id"])
            if latest.get("status") == "sent":
                with _db() as conn:
                    conn.execute("UPDATE messages SET delivery='sent',delivery_detail='sent' WHERE id=?", (message_id,))
                    return _message(conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone(), conn)
            raise HTTPException(409, "Message changed while sending; refresh its status")
        pane = _target(row["channel"], _panes())
        if not pane or not pane.get("agent"):
            with _db() as conn:
                conn.execute("UPDATE messages SET delivery='uncertain',transport_id=NULL,delivery_detail='Agent pane unavailable after cancellation' WHERE id=?", (message_id,))
            raise HTTPException(409, "Agent pane unavailable; delivery is unconfirmed")
        try:
            _send_saved(row, client, pane, force=True)
        except Exception:
            with _db() as conn:
                conn.execute("UPDATE messages SET delivery='uncertain',transport_id=NULL,delivery_detail='Urgent send unconfirmed',"
                             "transport_attempts=transport_attempts+1,transport_attempt_at=? WHERE id=?", (time.time(), message_id))
            raise HTTPException(503, "Urgent send unconfirmed; check agent activity before resending")
        with _db() as conn:
            return _message(conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone(), conn)


class BriefIn(BaseModel):
    channel: str
    body: str = Field(min_length=1, max_length=20000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


@app.post("/api/brief")
def post_brief(data: BriefIn, identity: Annotated[str, Depends(require_auth)]):
    if identity != "api":
        raise HTTPException(403, "API token required")
    if not _known_channel(data.channel):
        raise HTTPException(404, "Unknown channel")
    with _db() as conn:
        for attachment_id in data.attachment_ids:
            row = conn.execute("SELECT id FROM attachments WHERE id=? AND message_id IS NULL",
                               (attachment_id,)).fetchone()
            if not row:
                raise HTTPException(422, f"Attachment {attachment_id} is unavailable")
        cursor = conn.execute("INSERT INTO messages(channel,role,body) VALUES(?,?,?)",
                              (data.channel, "agent", data.body.strip()))
        for attachment_id in data.attachment_ids:
            conn.execute("UPDATE attachments SET message_id=? WHERE id=?",
                         (cursor.lastrowid, attachment_id))
        row = conn.execute("SELECT * FROM messages WHERE id=?", (cursor.lastrowid,)).fetchone()
        return _message(row, conn)


@app.get("/api/search")
def search(q: str, _: Annotated[str, Depends(require_auth)], channel: str | None = None, before: int | None = None):
    if len(q.strip()) < 2:
        return {"items": [], "has_more": False}
    if channel and not _known_channel(channel):
        raise HTTPException(404, "Unknown channel")
    clause = "AND channel=?" if channel else ""
    args = [f"%{q.strip()}%"] + ([channel] if channel else []) + [before or 2**63 - 1]
    with _db() as conn:
        rows = conn.execute(f"SELECT * FROM messages WHERE body LIKE ? {clause} AND id<? ORDER BY id DESC LIMIT 51", args).fetchall()
        return {"items": [_message(r, conn) for r in rows[:50]], "has_more": len(rows) > 50,
                "next_before": rows[49]["id"] if len(rows) >= 50 else None}


@app.post("/api/uploads")
async def upload(file: Annotated[UploadFile, File()], _: Annotated[str, Depends(require_auth)]):
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Files must be 25 MB or smaller")
    original = Path(file.filename or "upload").name
    original = re.sub(r"[^\w. ()-]", "_", original)[:180] or "upload"
    attachment_id = uuid.uuid4().hex
    path = UPLOADS / f"{attachment_id}_{original}"
    path.write_bytes(content)
    path.chmod(0o600)
    with _db() as conn:
        conn.execute("INSERT INTO attachments(id,filename,mime,size,path) VALUES(?,?,?,?,?)",
                     (attachment_id, original, file.content_type or "application/octet-stream", len(content), str(path)))
    return {"id": attachment_id, "filename": original, "mime": file.content_type, "size": len(content)}


@app.get("/api/uploads/{attachment_id}")
def download(attachment_id: str, _: Annotated[str, Depends(require_auth)], preview: bool = False):
    with _db() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Attachment not found")
    inline = preview and row["mime"] in {"image/png", "image/jpeg", "image/gif", "image/webp"}
    return FileResponse(row["path"], media_type=row["mime"], filename=row["filename"],
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff"})


def _read_pane_activity(pane: dict, *, lines: int = 80, client=None):
    result = (client or _flock()).call("read_pane", target=pane["pane_id"], lines=lines)
    return {"pane_id": pane["pane_id"],
            "status": (_presence(result["agent_status"]) if "agent_status" in result
                       else pane.get("status", _presence(pane.get("agent_status")))),
            "text": result.get("text", "")}


@app.get("/api/panes/activity")
def panes_activity(response: Response, _: Annotated[str, Depends(require_auth)]):
    # One refresh per process, shared by all browsers. Cache failures too, so
    # a disconnected daemon cannot cause a request storm. Never persist output.
    response.headers["Cache-Control"] = "no-store"
    with PANES_ACTIVITY_LOCK:
        if time.monotonic() >= PANES_ACTIVITY_CACHE["expires"]:
            try:
                client = _flock()
                client.timeout = 2.0
                panes = client.call("list_panes")["panes"]
                rows = build_roster([], panes, include_terminals=True)

                def read(row):
                    try:
                        output = _read_pane_activity(row, lines=40, client=client)
                        # Bound the response even if an upstream ignores lines.
                        output["text"] = "\n".join(output["text"].splitlines()[-40:])[-32000:]
                        return {**row, **output, "error": None}
                    except Exception:
                        return {**row, "text": "", "error": "Pane output unavailable"}

                with ThreadPoolExecutor(max_workers=4) as readers:
                    rows = list(readers.map(read, rows))
                data = {"panes": rows, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "refresh_after_seconds": PANES_ACTIVITY_TTL_S}
            except Exception:
                # Socket exceptions can contain terminal details; keep errors generic.
                data = None
            PANES_ACTIVITY_CACHE.update(data=data, expires=time.monotonic() + PANES_ACTIVITY_TTL_S)
        if PANES_ACTIVITY_CACHE["data"] is None:
            raise HTTPException(503, "Herdr panes unavailable", headers={"Cache-Control": "no-store"})
        return PANES_ACTIVITY_CACHE["data"]


@app.get("/api/activity")
def activity(channel: str, _: Annotated[str, Depends(require_auth)]):
    pane = _target(channel, _panes())
    if not pane:
        raise HTTPException(404, "Pane unavailable")
    return {"channel": channel, **_read_pane_activity(pane)}


@app.post("/api/poolrad-dashboard/refresh")
def refresh_poolrad_dashboard(_: Annotated[str, Depends(require_auth)]):
    script = DASHBOARD_DIR / "dashboard.py"
    if not script.is_file():
        raise HTTPException(404, "Poolrad dashboard unavailable")
    try:
        result = subprocess.run([sys.executable, str(script), "--repo", str(DASHBOARD_REPO), "render"], cwd=ROOT,
                                capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise HTTPException(503, "Poolrad dashboard refresh failed") from None
    if result.returncode or not (DASHBOARD_DIR / "dashboard.html").is_file():
        raise HTTPException(503, "Poolrad dashboard refresh failed")
    return {"refreshed": True}


@app.get("/api/poolrad-dashboard/dashboard.html")
def poolrad_dashboard_page(_: Annotated[str, Depends(require_auth)]):
    page = DASHBOARD_DIR / "dashboard.html"
    if not page.is_file():
        raise HTTPException(404, "Poolrad dashboard unavailable")
    return FileResponse(page, media_type="text/html", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'self'",
    })


@app.get("/api/poolrad-dashboard/state/reports/{filename}")
def poolrad_dashboard_report(filename: str, _: Annotated[str, Depends(require_auth)]):
    if filename not in DASHBOARD_REPORTS:
        raise HTTPException(404, "Report unavailable")
    report = DASHBOARD_DIR / "state" / "reports" / filename
    if not report.is_file():
        raise HTTPException(404, "Report unavailable")
    return FileResponse(report, media_type="text/plain", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/version")
def version():
    index = ROOT / "web" / "dist" / "index.html"
    if not index.exists():
        return {"version": "unbuilt"}
    match = re.search(r'<script[^>]+src="([^"]+)"', index.read_text())
    return {"version": match.group(1) if match else str(index.stat().st_mtime_ns)}


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
