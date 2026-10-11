"""Owner-only LAN dashboard for existing Herdr agents.

The web process never writes to a terminal directly: messages go through
Dunking Sheep's guarded send_text command. Herdr pane output is a live view,
not a durable or structured transcript; authored briefs are stored in SQLite.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
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
DUNKING_SHEEP = Path(os.getenv("DUNKING_SHEEP_DIR", ROOT.parent / "dunkingsheep"))
sys.path.insert(0, str(DUNKING_SHEEP))

CHANNELS = [
    {"id": "vp", "name": "VP of Agentry", "match": "vp of agentry", "kind": "active"},
    {"id": "poolrad", "name": "Poolrad PM", "match": "PM for Poolrad-decomp", "kind": "active"},
    {"id": "website", "name": "Website", "match": "Codex hunterdavis.com", "kind": "standby"},
    {"id": "racing", "name": "Slamdemonium", "match": "PM Claude Slam", "kind": "standby"},
    {"id": "tooling", "name": "Dunkies", "match": "dunky claude", "kind": "standby"},
    {"id": "server", "name": "MonkeyDLuffy", "match": "monkeydluffy", "kind": "monitor"},
]
CHANNEL_INDEX = {item["id"]: item for item in CHANNELS}
MAX_UPLOAD = 25 * 1024 * 1024
SESSIONS: dict[str, float] = {}
LOGIN_ATTEMPTS: dict[str, list[float]] = {}


def _db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _initialize():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                role TEXT NOT NULL,
                body TEXT NOT NULL,
                delivery TEXT NOT NULL DEFAULT 'posted',
                transport_id TEXT,
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
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        if "transport_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN transport_id TEXT")
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
    if cookie and SESSIONS.get(cookie, 0) > time.time():
        return "owner"
    raise HTTPException(401, "Sign in required")


class Login(BaseModel):
    password: str


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    _same_origin(request)
    addr = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = [t for t in LOGIN_ATTEMPTS.get(addr, []) if now - t < 300]
    if len(attempts) >= 8:
        raise HTTPException(429, "Too many attempts; retry in five minutes")
    record = _auth_record()
    digest = hashlib.pbkdf2_hmac("sha256", body.password.encode(), bytes.fromhex(record["salt"]), 400_000)
    if not hmac.compare_digest(digest, bytes.fromhex(record["digest"])):
        LOGIN_ATTEMPTS[addr] = attempts + [now]
        raise HTTPException(401, "Incorrect password")
    LOGIN_ATTEMPTS.pop(addr, None)
    session = secrets.token_urlsafe(32)
    SESSIONS[session] = now + 7 * 24 * 3600
    response.set_cookie("vp_session", session, httponly=True, samesite="strict", max_age=7 * 24 * 3600)
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request, response: Response, _: Annotated[str, Depends(require_auth)]):
    SESSIONS.pop(request.cookies.get("vp_session", ""), None)
    response.delete_cookie("vp_session")
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
    if not cfg:
        raise HTTPException(404, "Unknown channel")
    match = cfg["match"].casefold()
    for pane in panes:
        if pane.get("tab_label", "").casefold() == match:
            return pane
    for pane in panes:
        if match in pane.get("tab_label", "").casefold() or match in pane.get("workspace_label", "").casefold():
            return pane
    return None


def _presence(raw_status: str | None):
    # Herdr's "blocked" can mean a transient tool wait. It is not evidence of
    # a project blocker or a decision needed from the owner.
    return {"working": "working", "idle": "idle", "blocked": "waiting"}.get(raw_status, "unknown")


@app.get("/api/channels")
def channels(_: Annotated[str, Depends(require_auth)]):
    try:
        panes = _panes()
        daemon = True
    except HTTPException:
        panes, daemon = [], False
    rows = []
    for cfg in CHANNELS:
        pane = _target(cfg["id"], panes)
        rows.append({"id": cfg["id"], "name": cfg["name"], "kind": cfg["kind"],
                     "online": pane is not None, "status": _presence(pane.get("agent_status")) if pane else "offline",
                     "pane_id": pane.get("pane_id") if pane else None,
                     "can_message": bool(pane and pane.get("agent"))})
    return {"channels": rows, "daemon": daemon,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _message(row, conn):
    item = dict(row)
    item["attachments"] = [dict(r) for r in conn.execute(
        "SELECT id,filename,mime,size FROM attachments WHERE message_id=? ORDER BY created_at", (row["id"],))]
    return item


def _reconcile(channel: str):
    """Keep the UI's delivery label aligned with Dunking Sheep's queue state."""
    with _db() as conn:
        queued = conn.execute("SELECT id,transport_id FROM messages WHERE channel=? AND delivery='queued' ORDER BY id DESC LIMIT 50",
                              (channel,)).fetchall()
    if not queued:
        return
    try:
        client = _flock()
        legacy = {}
        if any(not row["transport_id"] for row in queued):
            records = client.call("list_messages")
            for item in records.get("queued", []) + records.get("recent", []):
                marker = re.search(r"\[VP web message #(\d+);", item.get("text", ""))
                if marker:
                    legacy[int(marker.group(1))] = item
        updates = []
        for row in queued:
            record = None
            transport_id = row["transport_id"]
            if transport_id:
                try:
                    record = client.call("get_message", message_id=transport_id)
                except Exception:
                    continue
            else:
                record = legacy.get(row["id"])
                transport_id = record.get("message_id") if record else None
            if record and record.get("status") in {"queued", "sent", "failed", "cancelled"}:
                updates.append((record["status"], transport_id, row["id"]))
        if updates:
            with _db() as conn:
                conn.executemany("UPDATE messages SET delivery=?,transport_id=? WHERE id=?", updates)
    except Exception:
        # Keep the last known state if the local daemon is temporarily unavailable.
        return


@app.get("/api/messages")
def messages(channel: str, _: Annotated[str, Depends(require_auth)], before: int | None = None, limit: int = 50):
    if channel not in CHANNEL_INDEX:
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


@app.post("/api/messages")
def post_message(data: MessageIn, identity: Annotated[str, Depends(require_auth)]):
    if data.channel not in CHANNEL_INDEX:
        raise HTTPException(404, "Unknown channel")
    if not data.body.strip() and not data.attachment_ids:
        raise HTTPException(422, "Message is empty")
    pane = _target(data.channel, _panes())
    if not pane or not pane.get("agent"):
        raise HTTPException(409, "No active agent is available in this channel")
    with _db() as conn:
        attachment_rows = []
        for attachment_id in data.attachment_ids:
            row = conn.execute("SELECT * FROM attachments WHERE id=? AND message_id IS NULL", (attachment_id,)).fetchone()
            if not row:
                raise HTTPException(422, f"Attachment {attachment_id} is unavailable")
            attachment_rows.append(row)
        cursor = conn.execute("INSERT INTO messages(channel,role,body,delivery) VALUES(?,?,?,?)",
                              (data.channel, "owner", data.body.strip(), "pending"))
        message_id = cursor.lastrowid
        for row in attachment_rows:
            conn.execute("UPDATE attachments SET message_id=? WHERE id=?", (message_id, row["id"]))
    references = "\n".join(f"- {row['filename']}: {row['path']}" for row in attachment_rows)
    prompt = data.body.strip()
    if references:
        prompt += f"\n\nAttached files on this host (read these paths directly):\n{references}"
    prompt += f"\n\n[VP web message #{message_id}; reply through vpctl brief --channel {data.channel} when a concise response is ready.]"
    try:
        result = _flock().call("send_text", target=pane["pane_id"], text=prompt,
                               hold_while_typing=True, wait_s=0)
        delivery = "queued" if result.get("queued") else "sent"
    except Exception as exc:
        delivery = "failed"
        result = {"error": str(exc)}
    with _db() as conn:
        conn.execute("UPDATE messages SET delivery=?,transport_id=? WHERE id=?",
                     (delivery, result.get("message_id"), message_id))
        row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        item = _message(row, conn)
    item["transport"] = result
    return item


class BriefIn(BaseModel):
    channel: str
    body: str = Field(min_length=1, max_length=20000)


@app.post("/api/brief")
def post_brief(data: BriefIn, identity: Annotated[str, Depends(require_auth)]):
    if identity != "api":
        raise HTTPException(403, "API token required")
    if data.channel not in CHANNEL_INDEX:
        raise HTTPException(404, "Unknown channel")
    with _db() as conn:
        cursor = conn.execute("INSERT INTO messages(channel,role,body) VALUES(?,?,?)",
                              (data.channel, "agent", data.body.strip()))
        row = conn.execute("SELECT * FROM messages WHERE id=?", (cursor.lastrowid,)).fetchone()
        return _message(row, conn)


@app.get("/api/search")
def search(q: str, _: Annotated[str, Depends(require_auth)], channel: str | None = None, before: int | None = None):
    if len(q.strip()) < 2:
        return {"items": [], "has_more": False}
    if channel and channel not in CHANNEL_INDEX:
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


@app.get("/api/activity")
def activity(channel: str, _: Annotated[str, Depends(require_auth)]):
    pane = _target(channel, _panes())
    if not pane:
        raise HTTPException(404, "Pane unavailable")
    result = _flock().call("read_pane", target=pane["pane_id"], lines=80)
    return {"channel": channel, "pane_id": pane["pane_id"],
            "status": _presence(result.get("agent_status")), "text": result.get("text", "")}


@app.get("/api/health")
def health():
    return {"ok": True}


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
