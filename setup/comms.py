#!/usr/bin/env python3
"""Agent comms — SQLite-backed group chat for multi-agent coordination.

Drop-in communication system that lets multiple Claude Code agents
(each in its own git worktree) coordinate via a shared SQLite database.
Messages are posted automatically by hooks and checked before each tool use.

Usage:
    python3 comms.py post -s "Web" "PR #12 ready for review"
    python3 comms.py check <session_id>
    python3 comms.py watch
    python3 comms.py chat
    python3 comms.py history [n]
    python3 comms.py status
    python3 comms.py assign <name> <agent-id>
    python3 comms.py auto-assign <session_id> <cwd>
    python3 comms.py resolve-name <session_id>
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# --- Configuration ---
# Override DB location with COMMS_DB_PATH env var, or defaults to ~/.claude/comms/messages.db
DB_PATH = Path(os.environ.get("COMMS_DB_PATH", Path.home() / ".claude" / "comms" / "messages.db"))

# Agent names that can be auto-assigned from directory suffixes.
# e.g. "taskflow-web" directory → "Web" agent name.
# Customize this list for your project's agents.
FRIENDLY_NAMES = os.environ.get("COMMS_AGENT_NAMES", "Sysadmin,Web,API,Data").split(",")

# Exact directory-to-name overrides. JSON string, e.g. '{"ops": "Sysadmin"}'
_DIR_MAP_RAW = os.environ.get("COMMS_DIR_MAP", '{}')
DIR_MAP = json.loads(_DIR_MAP_RAW)


def get_db():
    """Open (and auto-create) the SQLite comms database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            session_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS last_read (
            session_id TEXT PRIMARY KEY,
            message_id INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')),
            sender TEXT NOT NULL,
            channel TEXT DEFAULT 'general',
            message TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def resolve_name(session_id):
    """Return the friendly name for a session_id, or agent-{hash} if unassigned."""
    conn = get_db()
    row = conn.execute("SELECT name FROM agents WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        row = conn.execute("SELECT name FROM agents WHERE ? LIKE session_id || '%'", (session_id,)).fetchone()
    conn.close()
    if row:
        return row[0]
    return f"agent-{session_id[:8]}"


def auto_assign(session_id, cwd):
    """Auto-assign a friendly name based on directory suffix. e.g. taskflow-web -> Web."""
    dirname = os.path.basename(cwd).lower() if cwd else ""

    # Check exact directory overrides first
    if dirname in DIR_MAP:
        name = DIR_MAP[dirname]
        conn = get_db()
        conn.execute("DELETE FROM agents WHERE name = ?", (name,))
        conn.execute("INSERT OR REPLACE INTO agents (session_id, name) VALUES (?, ?)", (session_id, name))
        conn.commit()
        conn.close()
        return name

    # Check if dirname ends with -<name>
    name_map = {n.lower(): n for n in FRIENDLY_NAMES}
    for key, name in name_map.items():
        if dirname.endswith(f"-{key}"):
            conn = get_db()
            conn.execute("DELETE FROM agents WHERE name = ?", (name,))
            conn.execute("INSERT OR REPLACE INTO agents (session_id, name) VALUES (?, ?)", (session_id, name))
            conn.commit()
            conn.close()
            return name
    return None


def cmd_resolve_name(args):
    print(resolve_name(args.session_id))


def cmd_assign(args):
    """Assign a friendly name to a session. Shows unassigned sessions if no args."""
    conn = get_db()
    if not args.name:
        rows = conn.execute(
            "SELECT DISTINCT sender FROM messages ORDER BY id DESC LIMIT 20"
        ).fetchall()
        print("Recent senders:")
        for (sender,) in rows:
            tag = ""
            if sender.startswith("agent-"):
                sid_prefix = sender[6:]
                row = conn.execute("SELECT name FROM agents WHERE session_id LIKE ?", (sid_prefix + "%",)).fetchone()
                if row:
                    tag = f"  (= {row[0]})"
                else:
                    tag = "  [unassigned]"
            print(f"  {sender}{tag}")
        print(f"\nAvailable names: {', '.join(FRIENDLY_NAMES)}")
        print("Usage: comms assign <name> <agent-id or session_id prefix>")
        conn.close()
        return

    name = args.name
    agent_id = args.agent_id
    session_prefix = agent_id.removeprefix("agent-")

    conn.execute("DELETE FROM agents WHERE name = ?", (name,))
    row = conn.execute("SELECT session_id FROM agents WHERE session_id LIKE ?", (session_prefix + "%",)).fetchone()
    if row:
        conn.execute("UPDATE agents SET name = ? WHERE session_id = ?", (name, row[0]))
    else:
        conn.execute("INSERT OR REPLACE INTO agents (session_id, name) VALUES (?, ?)", (session_prefix, name))

    conn.commit()
    conn.close()
    print(f"Assigned: {agent_id} -> {name}")


def cmd_check(args):
    """Return unread messages for a session (from other senders). Updates cursor."""
    session_id = args.session_id
    my_name = resolve_name(session_id)
    conn = get_db()

    row = conn.execute("SELECT message_id FROM last_read WHERE session_id = ?", (session_id,)).fetchone()
    last_id = row[0] if row else 0

    rows = conn.execute(
        "SELECT id, timestamp, sender, message FROM messages WHERE id > ? AND sender != ? ORDER BY id",
        (last_id, my_name),
    ).fetchall()

    if rows:
        new_last = rows[-1][0]
        conn.execute(
            "INSERT OR REPLACE INTO last_read (session_id, message_id) VALUES (?, ?)",
            (session_id, new_last),
        )
        conn.commit()

        print(f"[comms] New messages (you are {my_name}):")
        for _id, ts, sender, message in rows:
            try:
                time_str = datetime.fromisoformat(ts).strftime("%H:%M:%S")
            except (ValueError, TypeError):
                time_str = "??:??:??"
            directed = message.lower().startswith(my_name.lower() + ":") or message.lower().startswith(my_name.lower() + ",")
            tag = " >>> FOR YOU" if directed else ""
            print(f"  {time_str} {sender}: {message}{tag}")

    conn.close()


def cmd_post(args):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (sender, channel, message) VALUES (?, ?, ?)",
        (args.sender, args.channel, " ".join(args.message)),
    )
    conn.commit()
    conn.close()


def format_row(row):
    _id, ts, sender, channel, message = row
    try:
        dt = datetime.fromisoformat(ts)
        time_str = dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        time_str = ts[:8] if ts else "??:??:??"
    return f"{time_str} {sender:<18} #{channel:<10} {message}"


def cmd_history(args):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, timestamp, sender, channel, message FROM messages ORDER BY id DESC LIMIT ?",
        (args.n,),
    ).fetchall()
    conn.close()
    if not rows:
        print("No messages yet.")
        return
    for row in reversed(rows):
        print(format_row(row))


def cmd_watch(args):
    conn = get_db()
    row = conn.execute("SELECT MAX(id) FROM messages").fetchone()
    last_id = row[0] or 0
    conn.close()

    print(f"[watching — polling every 1.5s, last_id={last_id}]")
    try:
        while True:
            conn = get_db()
            rows = conn.execute(
                "SELECT id, timestamp, sender, channel, message FROM messages WHERE id > ? ORDER BY id",
                (last_id,),
            ).fetchall()
            conn.close()
            for row in rows:
                print(format_row(row))
                last_id = row[0]
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n[stopped]")


def poll_new(last_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, timestamp, sender, channel, message FROM messages WHERE id > ? ORDER BY id",
        (last_id,),
    ).fetchall()
    conn.close()
    for row in rows:
        print(format_row(row))
        last_id = row[0]
    return last_id


def cmd_chat(args):
    import select
    import tty
    import termios

    conn = get_db()
    rows = conn.execute(
        "SELECT id, timestamp, sender, channel, message FROM messages ORDER BY id DESC LIMIT 10"
    ).fetchall()
    row = conn.execute("SELECT MAX(id) FROM messages").fetchone()
    last_id = row[0] or 0
    conn.close()

    if rows:
        for r in reversed(rows):
            print(format_row(r))
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
                        conn = get_db()
                        conn.execute(
                            "INSERT INTO messages (sender, channel, message) VALUES (?, ?, ?)",
                            ("nick", "general", input_buf.strip()),
                        )
                        conn.commit()
                        conn.close()
                    input_buf = ""
                elif ch == "\x7f" or ch == "\x08":
                    if input_buf:
                        input_buf = input_buf[:-1]
                        sys.stdout.write("\r> " + input_buf + " \b")
                        sys.stdout.flush()
                elif ch == "\x03":
                    raise KeyboardInterrupt
                else:
                    input_buf += ch
                    sys.stdout.write("\r> " + input_buf)
                    sys.stdout.flush()
            else:
                new_last = poll_new(last_id)
                if new_last != last_id:
                    last_id = new_last
                    if input_buf:
                        sys.stdout.write("> " + input_buf)
                        sys.stdout.flush()
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[left chat]")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def cmd_status(args):
    conn = get_db()
    cutoff = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = conn.execute(
        """
        SELECT sender,
               COUNT(*) as msg_count,
               MIN(timestamp) as first_seen,
               MAX(timestamp) as last_seen
        FROM messages
        WHERE timestamp >= ?
        GROUP BY sender
        ORDER BY last_seen DESC
        """,
        (cutoff,),
    ).fetchall()
    conn.close()

    if not rows:
        print("No agents active in the last 10 minutes.")
        return

    print(f"{'Sender':<20} {'Msgs':>5}  {'Last seen':<12}")
    print("-" * 40)
    for sender, count, first_seen, last_seen in rows:
        try:
            ls = datetime.fromisoformat(last_seen).strftime("%H:%M:%S")
        except (ValueError, TypeError):
            ls = last_seen[:8] if last_seen else "?"
        print(f"{sender:<20} {count:>5}  {ls:<12}")


def main():
    parser = argparse.ArgumentParser(description="Agent comms — group chat for Claude Code agents")
    sub = parser.add_subparsers(dest="command")

    p_post = sub.add_parser("post", help="Post a message")
    p_post.add_argument("-s", "--sender", default="nick")
    p_post.add_argument("-c", "--channel", default="general")
    p_post.add_argument("message", nargs="+")

    p_history = sub.add_parser("history", help="Show recent messages")
    p_history.add_argument("n", nargs="?", type=int, default=20)

    sub.add_parser("watch", help="Live tail of all messages")
    sub.add_parser("chat", help="Interactive chat mode")
    sub.add_parser("status", help="Show active agents")

    p_resolve = sub.add_parser("resolve-name", help="Resolve session to name")
    p_resolve.add_argument("session_id")

    p_assign = sub.add_parser("assign", help="Assign name to session")
    p_assign.add_argument("name", nargs="?", default=None)
    p_assign.add_argument("agent_id", nargs="?", default=None)

    p_check = sub.add_parser("check", help="Check for unread messages")
    p_check.add_argument("session_id")

    p_auto = sub.add_parser("auto-assign", help="Auto-assign name from directory")
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
        "auto-assign": lambda a: auto_assign(a.session_id, a.cwd),
    }[args.command](args)


if __name__ == "__main__":
    main()
