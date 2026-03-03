#!/usr/bin/env python3
"""Comms API server — FastAPI + DynamoDB backend for multi-agent coordination.

Single-file server implementing the comms API contract used by auto-agents.py.
Run with: uvicorn server:app --host 0.0.0.0 --port 8000
"""

import os
import time
from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel
from ulid import ULID

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

COMMS_API_SECRET = os.environ.get("COMMS_API_SECRET", "")
MESSAGES_TABLE = os.environ.get("DYNAMODB_MESSAGES_TABLE", "comms-messages")
AGENTS_TABLE = os.environ.get("DYNAMODB_AGENTS_TABLE", "comms-agents")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

TTL_DAYS = 30

# ──────────────────────────────────────────────────────────────
# DynamoDB setup
# ──────────────────────────────────────────────────────────────

DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "")

_dynamo_kwargs = {"region_name": AWS_REGION}
if DYNAMODB_ENDPOINT:
    _dynamo_kwargs["endpoint_url"] = DYNAMODB_ENDPOINT

dynamodb = boto3.resource("dynamodb", **_dynamo_kwargs)
messages_table = dynamodb.Table(MESSAGES_TABLE)
agents_table = dynamodb.Table(AGENTS_TABLE)

# ──────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────

app = FastAPI(title="Comms API", version="1.0")


# ──────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────


def verify_auth(authorization: Optional[str] = Header(None)):
    """Verify Bearer token on all comms endpoints."""
    if not COMMS_API_SECRET:
        return  # No secret configured — skip auth
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != COMMS_API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid token")


# ──────────────────────────────────────────────────────────────
# Request models
# ──────────────────────────────────────────────────────────────


class PostMessageRequest(BaseModel):
    sender: str
    message: str
    channel: str = "general"
    project: str = "general"


class RegisterAgentRequest(BaseModel):
    session_id: str
    cwd: str = ""
    name: Optional[str] = None
    project: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def ttl_epoch(days: int = TTL_DAYS) -> int:
    """Return a Unix epoch timestamp `days` in the future."""
    return int(time.time()) + (days * 86400)


def derive_agent_name(cwd: str) -> str:
    """Derive a friendly agent name from a working directory path.

    Strips a common repo prefix and title-cases the suffix.
    e.g. /home/user/myapp-web -> Web
         /home/user/myapp     -> Myapp
    """
    if not cwd:
        return "Agent"
    basename = os.path.basename(cwd.rstrip("/"))
    if not basename:
        return "Agent"
    # If there's a hyphen, take the last segment and title-case it
    parts = basename.split("-")
    if len(parts) > 1:
        return parts[-1].title()
    return basename.title()


# ──────────────────────────────────────────────────────────────
# POST /api/comms/messages
# ──────────────────────────────────────────────────────────────


@app.post("/api/comms/messages")
def post_message(body: PostMessageRequest, _=Depends(verify_auth)):
    sk = str(ULID())
    timestamp = datetime.now(timezone.utc).isoformat()

    messages_table.put_item(Item={
        "channel": body.channel,
        "sk": sk,
        "sender": body.sender,
        "message": body.message,
        "project": body.project,
        "timestamp": timestamp,
        "ttl": ttl_epoch(),
    })

    return {"sk": sk, "timestamp": timestamp}


# ──────────────────────────────────────────────────────────────
# GET /api/comms/messages
# ──────────────────────────────────────────────────────────────


@app.get("/api/comms/messages")
def get_messages(
    limit: int = Query(20, ge=1, le=200),
    project: Optional[str] = Query(None),
    after: Optional[str] = Query(None),
    _=Depends(verify_auth),
):
    if project:
        # Use the project GSI
        key_cond = Key("project").eq(project)
        if after:
            key_cond = key_cond & Key("sk").gt(after)
        resp = messages_table.query(
            IndexName="project-index",
            KeyConditionExpression=key_cond,
            ScanIndexForward=True,
            Limit=limit,
        )
    else:
        # Query the main table (channel = "general")
        key_cond = Key("channel").eq("general")
        if after:
            key_cond = key_cond & Key("sk").gt(after)
        resp = messages_table.query(
            KeyConditionExpression=key_cond,
            ScanIndexForward=True,
            Limit=limit,
        )

    messages = resp.get("Items", [])
    # Strip internal fields
    for msg in messages:
        msg.pop("ttl", None)
        msg.pop("channel", None)

    return {"messages": messages}


# ──────────────────────────────────────────────────────────────
# GET /api/comms/check
# ──────────────────────────────────────────────────────────────


@app.get("/api/comms/check")
def check_messages(
    session_id: str = Query(...),
    _=Depends(verify_auth),
):
    # Look up agent
    agent_resp = agents_table.get_item(Key={"sessionId": session_id})
    agent = agent_resp.get("Item")

    if not agent:
        # Agent not yet registered — return empty result instead of 404.
        # The session-start hook may not have fired yet, or registration
        # may have failed.  The client treats this the same as "no messages".
        return {"agentName": "Unknown", "project": "general", "messages": []}

    last_cursor = agent.get("lastCursor", "")
    agent_project = agent.get("project", "general")
    agent_name = agent.get("name", "Agent")

    # Determine if cross-project (name-based heuristic not needed server-side;
    # just return messages for the agent's project, or all if project is "general")
    if agent_project and agent_project != "general":
        key_cond = Key("project").eq(agent_project)
        if last_cursor:
            key_cond = key_cond & Key("sk").gt(last_cursor)
        resp = messages_table.query(
            IndexName="project-index",
            KeyConditionExpression=key_cond,
            ScanIndexForward=True,
            Limit=100,
        )
    else:
        key_cond = Key("channel").eq("general")
        if last_cursor:
            key_cond = key_cond & Key("sk").gt(last_cursor)
        resp = messages_table.query(
            KeyConditionExpression=key_cond,
            ScanIndexForward=True,
            Limit=100,
        )

    messages = resp.get("Items", [])

    # Filter out messages sent by this agent (don't echo back)
    messages = [m for m in messages if m.get("sender") != agent_name]

    # Update cursor to latest message
    if messages:
        new_cursor = messages[-1]["sk"]
        agents_table.update_item(
            Key={"sessionId": session_id},
            UpdateExpression="SET lastCursor = :c",
            ExpressionAttributeValues={":c": new_cursor},
        )

    # Strip internal fields
    for msg in messages:
        msg.pop("ttl", None)
        msg.pop("channel", None)

    return {
        "agentName": agent_name,
        "project": agent_project,
        "messages": messages,
    }


# ──────────────────────────────────────────────────────────────
# POST /api/comms/agents
# ──────────────────────────────────────────────────────────────


@app.post("/api/comms/agents")
def register_agent(body: RegisterAgentRequest, _=Depends(verify_auth)):
    session_id = body.session_id
    name = body.name or derive_agent_name(body.cwd)
    project = body.project or "general"

    # Upsert: update name/project/cwd but preserve lastCursor if it exists
    agents_table.update_item(
        Key={"sessionId": session_id},
        UpdateExpression=(
            "SET #n = :name, #p = :project, cwd = :cwd, "
            "createdAt = if_not_exists(createdAt, :now), "
            "lastCursor = if_not_exists(lastCursor, :empty), "
            "ttl = :ttl"
        ),
        ExpressionAttributeNames={"#n": "name", "#p": "project"},
        ExpressionAttributeValues={
            ":name": name,
            ":project": project,
            ":cwd": body.cwd,
            ":now": datetime.now(timezone.utc).isoformat(),
            ":empty": "",
            ":ttl": ttl_epoch(),
        },
    )

    return {
        "name": name,
        "sessionId": session_id,
        "project": project,
        "cwd": body.cwd,
    }


# ──────────────────────────────────────────────────────────────
# GET /api/comms/agents
# ──────────────────────────────────────────────────────────────


@app.get("/api/comms/agents")
def get_agents(
    session_id: Optional[str] = Query(None),
    _=Depends(verify_auth),
):
    if session_id:
        resp = agents_table.get_item(Key={"sessionId": session_id})
        item = resp.get("Item")
        if not item:
            return {"agent": None}
        item.pop("ttl", None)
        item.pop("lastCursor", None)
        return {"agent": item}

    # Scan all agents
    resp = agents_table.scan()
    agents = resp.get("Items", [])
    for a in agents:
        a.pop("ttl", None)
        a.pop("lastCursor", None)
    return {"agents": agents}
