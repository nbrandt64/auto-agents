#!/usr/bin/env python3
"""Agent comms — HTTP API-backed chat for multi-agent coordination."""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "comms" / "config"

FRIENDLY_NAMES = ["Sysadmin", "Web", "App", "Misc", "Integr1", "Integr2", "AlexOps", "AlexMisc"]

# Agents that should see messages from ALL projects (cross-project roles)
CROSS_PROJECT_AGENTS = ["Sysadmin", "AlexOps"]

# Known project directory prefixes → project name.
PROJECT_DIRS = {
    "zenvoy": "zenvoy",
    "signaturefinder": "signaturefinder",
    "poker-ai": "poker-ai",
    "github": "zenvoy",
}

# Exact directory-to-name mappings
DIR_MAP = {"github": "Sysadmin", "signaturefinder": "SignatureFinder", "poker-ai": "PokerAI", "zenvoy-ops": "AlexOps"}


def detect_project(cwd):
    """Derive project name from a working directory path."""
    if not cwd:
        return "general"
    dirname = os.path.basename(cwd).lower()
    if dirname in PROJECT_DIRS:
        return PROJECT_DIRS[dirname]
    for prefix, project in PROJECT_DIRS.items():
        if dirname.startswith(prefix + "-"):
            return project
    return "general"


def load_config():
    """Load API URL and secret from config file or env vars."""
    url = os.environ.get("COMMS_API_URL", "")
    secret = os.environ.get("COMMS_API_SECRET", "")

    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == "COMMS_API_URL" and not os.environ.get("COMMS_API_URL"):
                    url = val
                elif key == "COMMS_API_SECRET" and not os.environ.get("COMMS_API_SECRET"):
                    secret = val

    if not url:
        print("Error: COMMS_API_URL not set. Create ~/.claude/comms/config or set env var.", file=sys.stderr)
        sys.exit(1)

    return url.rstrip("/"), secret


def api_call(method, path, data=None, params=None, fail_silent=False):
    """Make an HTTP API call. Returns parsed JSON or None on failure."""
    base_url, secret = load_config()
    url = f"{base_url}{path}"

    if params:
        query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items() if v is not None)
        if query:
            url += f"?{query}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {secret}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if fail_silent:
            return None
        body_text = ""
        try:
            body_text = e.read().decode()
        except Exception:
            pass
        print(f"API error {e.code}: {body_text}", file=sys.stderr)
        return None
    except Exception as e:
        if fail_silent:
            return None
        print(f"API connection error: {e}", file=sys.stderr)
        return None


def resolve_name(session_id):
    """Return the friendly name for a session_id."""
    result = api_call("GET", "/api/comms/agents", params={"session_id": session_id}, fail_silent=True)
    if result and result.get("agent") and result["agent"].get("name"):
        return result["agent"]["name"]
    return f"agent-{session_id[:8]}"


def auto_assign(session_id, cwd):
    """Auto-assign a friendly name and project based on directory."""
    result = api_call("POST", "/api/comms/agents", data={"session_id": session_id, "cwd": cwd})
    if result and result.get("name"):
        return result["name"]
    return None


def cmd_resolve_name(args):
    print(resolve_name(args.session_id))


def cmd_assign(args):
    """Assign a friendly name to a session."""
    if not args.name:
        # List registered agents
        result = api_call("GET", "/api/comms/agents")
        if result and result.get("agents"):
            print("Registered agents:")
            for a in result["agents"]:
                print(f"  {a.get('name', '?'):<18} session={a.get('sessionId', '?')[:12]}  project={a.get('project', '?')}")
        else:
            print("No agents registered.")
        print(f"\nAvailable names: {', '.join(FRIENDLY_NAMES)}")
        print("Usage: comms assign <name> <session_id>")
        return

    result = api_call("POST", "/api/comms/agents", data={"session_id": args.agent_id, "name": args.name})
    if result:
        print(f"Assigned: {args.agent_id} → {result.get('name', args.name)}")
    else:
        print("Failed to assign name.", file=sys.stderr)


def cmd_check(args):
    """Return unread messages for a session. Updates cursor server-side."""
    session_id = args.session_id
    result = api_call("GET", "/api/comms/check", params={"session_id": session_id}, fail_silent=True)

    if not result or not result.get("messages"):
        return

    agent_name = result.get("agentName", "?")
    project = result.get("project", "?")
    messages = result["messages"]

    if messages:
        print(f"[comms] New messages (you are {agent_name}, project={project}):")
        for msg in messages:
            ts = msg.get("timestamp", "")
            sender = msg.get("sender", "?")
            text = msg.get("message", "")
            msg_project = msg.get("project", "")
            try:
                time_str = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
            except (ValueError, TypeError):
                time_str = "??:??:??"
            directed = text.lower().startswith(agent_name.lower() + ":") or text.lower().startswith(agent_name.lower() + ",")
            tag = " >>> FOR YOU" if directed else ""
            proj_tag = f" [{msg_project}]" if agent_name in CROSS_PROJECT_AGENTS and msg_project else ""
            print(f"  {time_str}{proj_tag} {sender}: {text}{tag}")


def cmd_post(args):
    """Post a message."""
    message = " ".join(args.message)
    result = api_call("POST", "/api/comms/messages", data={
        "sender": args.sender,
        "message": message,
        "channel": args.channel,
        "project": args.project,
    })
    if not result:
        print("Warning: failed to post message", file=sys.stderr)


def format_msg(msg):
    """Format a message dict for display."""
    ts = msg.get("timestamp", "")
    sender = msg.get("sender", "?")
    text = msg.get("message", "")
    project = msg.get("project", "general")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        time_str = dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        time_str = ts[:8] if ts else "??:??:??"
    return f"{time_str} [{project}] {sender:<18} {text}"


def cmd_history(args):
    """Show recent messages."""
    params = {"limit": args.n}
    if args.project:
        params["project"] = args.project
    result = api_call("GET", "/api/comms/messages", params=params)
    if not result or not result.get("messages"):
        print("No messages yet.")
        return
    for msg in result["messages"]:
        print(format_msg(msg))


def cmd_watch(args):
    """Watch for new messages (polling)."""
    # Get initial cursor from latest messages
    result = api_call("GET", "/api/comms/messages", params={"limit": 1})
    last_sk = None
    if result and result.get("messages"):
        last_sk = result["messages"][-1].get("sk")

    print(f"[watching — polling every 1.5s]")
    try:
        while True:
            params = {"limit": 50}
            if last_sk:
                params["after"] = last_sk
            result = api_call("GET", "/api/comms/messages", params=params, fail_silent=True)
            if result and result.get("messages"):
                for msg in result["messages"]:
                    print(format_msg(msg))
                    sk = msg.get("sk")
                    if sk:
                        last_sk = sk
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n[stopped]")


def cmd_chat(args):
    """Interactive chat mode."""
    import select
    import tty
    import termios

    # Show recent messages for context
    result = api_call("GET", "/api/comms/messages", params={"limit": 10})
    last_sk = None
    if result and result.get("messages"):
        for msg in result["messages"]:
            print(format_msg(msg))
            sk = msg.get("sk")
            if sk:
                last_sk = sk
        print()

    print("[chat mode — type message + enter to send, ctrl-c to quit]")
    print()

    input_buf = ""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        while True:
            if select.select([sys.stdin], [], [], 0.0)[0]:
                ch = sys.stdin.read(1)
                if ch == "\n" or ch == "\r":
                    if input_buf.strip():
                        sys.stdout.write("\r" + " " * (len(input_buf) + 2) + "\r")
                        sys.stdout.flush()
                        api_call("POST", "/api/comms/messages", data={
                            "sender": "nick",
                            "message": input_buf.strip(),
                            "channel": "general",
                            "project": args.project,
                        })
                    input_buf = ""
                elif ch == "\x7f" or ch == "\x08":  # backspace
                    if input_buf:
                        input_buf = input_buf[:-1]
                        sys.stdout.write("\r> " + input_buf + " \b")
                        sys.stdout.flush()
                elif ch == "\x03":  # ctrl-c
                    raise KeyboardInterrupt
                else:
                    input_buf += ch
                    sys.stdout.write("\r> " + input_buf)
                    sys.stdout.flush()
            else:
                # Poll for new messages
                params = {"limit": 50}
                if last_sk:
                    params["after"] = last_sk
                result = api_call("GET", "/api/comms/messages", params=params, fail_silent=True)
                if result and result.get("messages"):
                    for msg in result["messages"]:
                        print(format_msg(msg))
                        sk = msg.get("sk")
                        if sk:
                            last_sk = sk
                    if input_buf:
                        sys.stdout.write("> " + input_buf)
                        sys.stdout.flush()
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[left chat]")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def cmd_status(args):
    """Show registered agents."""
    result = api_call("GET", "/api/comms/agents")
    if not result or not result.get("agents"):
        print("No agents registered.")
        return

    print(f"{'Name':<20} {'Project':<18} {'Session':<14} {'Created':<12}")
    print("-" * 64)
    for a in result["agents"]:
        name = a.get("name", "?")
        project = a.get("project", "?")
        sid = a.get("sessionId", "?")[:12]
        created = a.get("createdAt", "?")
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%H:%M:%S")
        except (ValueError, TypeError):
            ts = created[:8] if created else "?"
        print(f"{name:<20} {project:<18} {sid:<14} {ts:<12}")


def main():
    parser = argparse.ArgumentParser(description="Agent comms")
    sub = parser.add_subparsers(dest="command")

    p_post = sub.add_parser("post")
    p_post.add_argument("-s", "--sender", default="nick")
    p_post.add_argument("-c", "--channel", default="general")
    p_post.add_argument("-p", "--project", default="general")
    p_post.add_argument("message", nargs="+")

    p_history = sub.add_parser("history")
    p_history.add_argument("n", nargs="?", type=int, default=20)
    p_history.add_argument("-p", "--project", default=None, help="Filter by project")

    sub.add_parser("watch")
    p_chat = sub.add_parser("chat")
    p_chat.add_argument("-p", "--project", default="general", help="Project to scope messages to")
    sub.add_parser("status")

    p_resolve = sub.add_parser("resolve-name")
    p_resolve.add_argument("session_id")

    p_assign = sub.add_parser("assign")
    p_assign.add_argument("name", nargs="?", default=None)
    p_assign.add_argument("agent_id", nargs="?", default=None)

    p_check = sub.add_parser("check")
    p_check.add_argument("session_id")

    p_auto = sub.add_parser("auto-assign")
    p_auto.add_argument("session_id")
    p_auto.add_argument("cwd")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {
        "post": cmd_post,
        "history": cmd_history,
        "watch": cmd_watch,
        "chat": cmd_chat,
        "status": cmd_status,
        "resolve-name": cmd_resolve_name,
        "assign": cmd_assign,
        "check": cmd_check,
        "auto-assign": lambda a: print(auto_assign(a.session_id, a.cwd) or ""),
    }[args.command](args)


if __name__ == "__main__":
    main()
