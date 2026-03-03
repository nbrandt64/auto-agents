#!/usr/bin/env python3
"""auto-agents — unified CLI for multi-agent project setup and coordination.

Interactive menu + REPL for setup tasks and runtime operations.
Zero external dependencies — Python stdlib only.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Constants & ANSI
# ──────────────────────────────────────────────────────────────

VERSION = "1.0"

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
CLEAR_LINE = "\033[2K"

COMMS_DIR = Path.home() / ".claude" / "comms"
SCRIPTS_DIR = Path.home() / ".claude" / "scripts"
SKILLS_DIR = Path.home() / ".claude" / "skills"
CONFIG_PATH = COMMS_DIR / "config"
PROJECTS_PATH = COMMS_DIR / "projects.json"
HISTORY_PATH = COMMS_DIR / "repl_history"
MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB

# ──────────────────────────────────────────────────────────────
# Config Layer — projects.json read/write
# ──────────────────────────────────────────────────────────────


def load_projects():
    """Load projects registry from ~/.claude/comms/projects.json."""
    if not PROJECTS_PATH.exists():
        return {"version": 1, "projects": {}}
    try:
        return json.loads(PROJECTS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "projects": {}}


def save_projects(data):
    """Save projects registry."""
    COMMS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_PATH.write_text(json.dumps(data, indent=2) + "\n")


def detect_current_project():
    """Detect project from current working directory.

    Returns (project_name, project_config) or (None, None).
    """
    return _detect_project_from_path(os.getcwd())


def _detect_project_from_path(cwd):
    """Detect project from an arbitrary path."""
    projects = load_projects().get("projects", {})
    for name, config in projects.items():
        project_path = config.get("path", "")
        if not project_path:
            continue
        # cwd is the project dir itself or a subdirectory
        if cwd == project_path or cwd.startswith(project_path + os.sep):
            return name, config
        # cwd is a worktree sibling (e.g. myapp-web next to myapp)
        parent = os.path.dirname(project_path)
        base = os.path.basename(project_path)
        cwd_base = os.path.basename(cwd)
        if os.path.dirname(cwd) == parent and cwd_base.startswith(base + "-"):
            return name, config
    return None, None


def detect_project_for_hook(cwd):
    """Detect project name from a given cwd (for hooks / comms). Returns 'general' if unknown."""
    name, _ = _detect_project_from_path(cwd)
    return name or "general"


def get_cross_project_agents():
    """Return list of agent names marked as cross-project across all projects."""
    names = []
    for _, pconfig in load_projects().get("projects", {}).items():
        for suffix, agent in pconfig.get("agents", {}).items():
            if agent.get("cross_project"):
                n = agent.get("name", suffix.title())
                if n not in names:
                    names.append(n)
    return names


# ──────────────────────────────────────────────────────────────
# Comms API Layer (ported from comms.py)
# ──────────────────────────────────────────────────────────────

_config_cache = None


def load_config():
    """Load API URL and secret from config file or env vars."""
    global _config_cache
    if _config_cache:
        return _config_cache

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
        return None, None

    _config_cache = (url.rstrip("/"), secret)
    return _config_cache


def api_call(method, path, data=None, params=None, fail_silent=False):
    """Make an HTTP API call. Returns parsed JSON or None on failure."""
    url, secret = load_config()
    if not url:
        if not fail_silent:
            print(f"  {RED}Error: COMMS_API_URL not configured. Run /install to set up.{RESET}", file=sys.stderr)
        return None

    full_url = f"{url}{path}"
    if params:
        query = "&".join(
            f"{k}={urllib.request.quote(str(v))}" for k, v in params.items() if v is not None
        )
        if query:
            full_url += f"?{query}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(full_url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {secret}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read(MAX_RESPONSE_SIZE).decode())
    except urllib.error.HTTPError as e:
        if fail_silent:
            return None
        body_text = ""
        try:
            body_text = e.read().decode()
        except Exception:
            pass
        print(f"  API error {e.code}: {body_text}", file=sys.stderr)
        return None
    except Exception as e:
        if fail_silent:
            return None
        print(f"  API connection error: {e}", file=sys.stderr)
        return None


def parse_time(ts):
    """Parse an ISO timestamp to HH:MM:SS."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return ts[:8] if ts else "??:??:??"


def format_msg(msg):
    """Format a message dict for display."""
    ts = msg.get("timestamp", "")
    sender = msg.get("sender", "?")
    text = msg.get("message", "")
    project = msg.get("project", "general")
    time_str = parse_time(ts)
    return f"  {DIM}{time_str}{RESET} [{project}] {BOLD}{sender:<12}{RESET} {text}"


def resolve_name(session_id):
    """Return the friendly name for a session_id."""
    result = api_call("GET", "/api/comms/agents", params={"session_id": session_id}, fail_silent=True)
    if result and result.get("agent") and result["agent"].get("name"):
        return result["agent"]["name"]
    return f"agent-{session_id[:8]}"


def resolve_name_from_cwd(cwd):
    """Resolve agent name from projects.json by matching cwd to a project's worktree.

    Returns (agent_display_name, project_name) or (None, None).
    """
    if not cwd:
        return None, None
    cwd_base = os.path.basename(cwd)
    projects = load_projects().get("projects", {})
    for pname, pconfig in projects.items():
        project_path = pconfig.get("path", "")
        if not project_path:
            continue
        repo_name = os.path.basename(project_path)
        parent = os.path.dirname(project_path)
        for suffix, agent in pconfig.get("agents", {}).items():
            expected_dir = f"{repo_name}-{suffix}"
            expected_path = os.path.join(parent, expected_dir)
            if cwd == expected_path or cwd_base == expected_dir:
                return agent.get("name", suffix.title()), pname
    return None, None


def auto_assign(session_id, cwd):
    """Auto-assign a friendly name and project based on directory.

    First tries local projects.json, then falls back to API.
    """
    # Try local resolution first
    local_name, local_project = resolve_name_from_cwd(cwd)
    if local_name:
        # Register with API using the locally-resolved name
        api_call(
            "POST",
            "/api/comms/agents",
            data={"session_id": session_id, "cwd": cwd, "name": local_name, "project": local_project},
            fail_silent=True,
        )
        return local_name

    # Fall back to API-side resolution
    result = api_call("POST", "/api/comms/agents", data={"session_id": session_id, "cwd": cwd})
    if result and result.get("name"):
        return result["name"]
    return None


# ──────────────────────────────────────────────────────────────
# Interactive Menu (arrow-key navigation, ANSI rendering)
# ──────────────────────────────────────────────────────────────


def interactive_menu(title, options):
    """Arrow-key navigable menu. Returns selected option index or -1 for quit.

    options: list of (label, shortcut, description) tuples.
    """
    import termios
    import tty

    selected = 0
    n = len(options)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    def render():
        sys.stdout.write("\r")
        for i, (label, shortcut, _desc) in enumerate(options):
            sys.stdout.write(CLEAR_LINE)
            if i == selected:
                sys.stdout.write(f"  {GREEN}>{RESET} {BOLD}{label:<28}{RESET} {DIM}{shortcut}{RESET}\r\n")
            else:
                sys.stdout.write(f"    {label:<28} {DIM}{shortcut}{RESET}\r\n")
        sys.stdout.write(f"\r\n{CLEAR_LINE}  {DIM}[↑↓ to move, Enter to select, q to quit]{RESET}")
        # Move cursor back up to top of menu
        sys.stdout.write(f"\033[{n + 1}A")
        sys.stdout.flush()

    def clear_menu():
        sys.stdout.write("\r")
        for _ in range(n + 1):
            sys.stdout.write(CLEAR_LINE + "\r\n")
        sys.stdout.write(f"\033[{n + 1}A")
        sys.stdout.flush()

    try:
        # Print header before entering raw mode
        print()
        print(f"  {BOLD}╭{'─' * 35}╮{RESET}")
        print(f"  {BOLD}│  auto-agents v{VERSION:<20}│{RESET}")
        print(f"  {BOLD}╰{'─' * 35}╯{RESET}")
        print()
        print(f"  {BOLD}? {title}{RESET}")
        print()
        sys.stdout.flush()

        tty.setraw(fd)
        render()

        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":  # escape sequence
                sys.stdin.read(1)  # skip [
                arrow = sys.stdin.read(1)
                if arrow == "A":
                    selected = max(0, selected - 1)
                elif arrow == "B":
                    selected = min(n - 1, selected + 1)
            elif ch in ("\r", "\n"):
                clear_menu()
                return selected
            elif ch == "q" or ch == "\x03":  # q or Ctrl+C
                clear_menu()
                return -1
            render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        # Move cursor past the menu area
        sys.stdout.write("\n" * (n + 1))
        sys.stdout.flush()


# ──────────────────────────────────────────────────────────────
# REPL (slash commands, tab completion, history)
# ──────────────────────────────────────────────────────────────

# Forward declaration — filled in after all command definitions
COMMANDS = {}


def cmd_help(_args=""):
    """Show available commands."""
    print()
    print(f"  {BOLD}Setup:{RESET}")
    print(f"    /doctor          Check prerequisites and environment")
    print(f"    /install         One-time global setup")
    print(f"    /init            Set up a new project")
    print(f"    /add-agent       Add an agent to current project")
    print(f"    /remove-agent    Remove an agent")
    print(f"    /menu            Show interactive setup menu")
    print()
    print(f"  {BOLD}Runtime:{RESET}")
    print(f"    /status          Show project config and agents")
    print(f"    /watch           Watch group chat (live)")
    print(f"    /chat            Interactive group chat")
    print(f"    /post            Send a message: /post Agent \"message\"")
    print(f"    /history         Show recent messages")
    print()
    print(f"  {BOLD}Other:{RESET}")
    print(f"    /help            Show this help")
    print(f"    /exit            Exit auto-agents")
    print()


def repl(project_name=None):
    """Interactive REPL with slash commands."""
    import readline

    def completer(text, state):
        matches = [c for c in COMMANDS if c.startswith(text)]
        return matches[state] if state < len(matches) else None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" ")

    # Persistent history
    COMMS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(str(HISTORY_PATH))
    except (FileNotFoundError, OSError):
        pass

    if project_name:
        project_data = load_projects().get("projects", {}).get(project_name, {})
        agent_count = len(project_data.get("agents", {}))
        s = "s" if agent_count != 1 else ""
        print(f"\n  {BOLD}auto-agents v{VERSION}{RESET} — {CYAN}{project_name}{RESET} ({agent_count} agent{s})")
        print(f"  Type {BOLD}/help{RESET} for commands, {BOLD}/menu{RESET} for setup options\n")
    else:
        print(f"\n  {BOLD}auto-agents v{VERSION}{RESET}")
        print(f"  Type {BOLD}/help{RESET} for commands\n")

    prompt = "auto-agents> "

    while True:
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line == "/exit":
            break

        parts = line.split(None, 1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""

        if cmd_name in COMMANDS:
            handler = COMMANDS[cmd_name]
            if handler is not None:
                try:
                    handler(cmd_args)
                except KeyboardInterrupt:
                    print()
                except Exception as e:
                    print(f"  {RED}Error: {e}{RESET}")
        else:
            print(f"  Unknown command: {cmd_name}. Type /help for available commands.")

    try:
        readline.write_history_file(str(HISTORY_PATH))
    except OSError:
        pass


# ──────────────────────────────────────────────────────────────
# /doctor — Check prerequisites and environment
# ──────────────────────────────────────────────────────────────


def cmd_doctor(_args=""):
    """Check prerequisites and environment."""
    print()
    print(f"  {BOLD}Prerequisites:{RESET}")

    checks = [
        ("python3", ["python3", "--version"]),
        ("git", ["git", "--version"]),
        ("gh", ["gh", "--version"]),
        ("claude", ["claude", "--version"]),
    ]

    missing_cmds = []
    for name, cmd in checks:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.strip().split("\n")[0]
                # Clean up version string
                version = version.replace("Python ", "").replace("git version ", "")
                version = version.split("(")[0].strip()
                path = shutil.which(name) or "?"
                print(f"    {GREEN}[ok]{RESET}   {name:<12} {DIM}{version:<18} {path}{RESET}")
            else:
                print(f"    {RED}[MISS]{RESET} {name:<12} {DIM}—{RESET}")
                missing_cmds.append(name)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"    {RED}[MISS]{RESET} {name:<12} {DIM}— not found{RESET}")
            missing_cmds.append(name)

    print()
    print(f"  {BOLD}Setup:{RESET}")

    script_path = SCRIPTS_DIR / "auto-agents.py"
    if script_path.exists():
        print(f"    {GREEN}[ok]{RESET}   Scripts              {DIM}{script_path}{RESET}")
    else:
        print(f"    {RED}[MISS]{RESET} Scripts              {DIM}{script_path} (not found){RESET}")

    if CONFIG_PATH.exists():
        print(f"    {GREEN}[ok]{RESET}   Comms config         {DIM}{CONFIG_PATH}{RESET}")
    else:
        print(f"    {RED}[MISS]{RESET} Comms config         {DIM}{CONFIG_PATH} (not found){RESET}")

    projects = load_projects().get("projects", {})
    count = len(projects)
    if count:
        print(f"    {GREEN}[ok]{RESET}   Projects ({count})         {DIM}{PROJECTS_PATH}{RESET}")
    else:
        print(f"    {YELLOW}[—]{RESET}    Projects (0)         {DIM}{PROJECTS_PATH}{RESET}")

    if SKILLS_DIR.exists() and any(SKILLS_DIR.iterdir()):
        skill_count = sum(1 for d in SKILLS_DIR.iterdir() if d.is_dir())
        print(f"    {GREEN}[ok]{RESET}   Skills ({skill_count})            {DIM}{SKILLS_DIR}{RESET}")
    else:
        print(f"    {RED}[MISS]{RESET} Skills               {DIM}{SKILLS_DIR} (not found){RESET}")

    # Fix suggestions
    needs_fix = bool(missing_cmds) or not script_path.exists() or not CONFIG_PATH.exists()
    if needs_fix:
        print()
        print(f"  {BOLD}To fix:{RESET}")
        if "gh" in missing_cmds:
            hint = "brew install gh" if sys.platform == "darwin" else "https://cli.github.com/"
            print(f"    gh:      {DIM}{hint}{RESET}")
        if "claude" in missing_cmds:
            print(f"    claude:  {DIM}npm install -g @anthropic-ai/claude-code{RESET}")
        if not script_path.exists() or not CONFIG_PATH.exists():
            print(f"    setup:   {DIM}/install{RESET}")
        if not (SKILLS_DIR.exists() and any(SKILLS_DIR.iterdir())):
            print(f"    skills:  {DIM}/install (or copy setup/skills/ to {SKILLS_DIR}){RESET}")
    print()


# ──────────────────────────────────────────────────────────────
# /status — Show project config and agents
# ──────────────────────────────────────────────────────────────


def cmd_status(_args=""):
    """Show project config and agents."""
    project_name, project = detect_current_project()

    if not project:
        # Attempt to show API status
        result = api_call("GET", "/api/comms/agents", fail_silent=True)
        if result and result.get("agents"):
            print()
            print(f"  {BOLD}Registered agents (API):{RESET}")
            print(f"  {'Name':<18} {'Project':<14} {'Session':<14} {'Created':<12}")
            print(f"  {'─' * 58}")
            for a in result["agents"]:
                name = a.get("name", "?")
                proj = a.get("project", "?")
                sid = a.get("sessionId", "?")[:12]
                created = a.get("createdAt", "?")
                print(f"  {name:<18} {proj:<14} {DIM}{sid:<14} {parse_time(created)}{RESET}")
            print()
        else:
            print(f"\n  No project detected in current directory.")
            print(f"  Run {BOLD}/init{RESET} to set up a project.\n")
        return

    print()
    print(f"  {BOLD}Project:{RESET} {CYAN}{project_name}{RESET}")
    if project.get("repo"):
        print(f"  {BOLD}Repo:{RESET}    {project['repo']}")
    print(f"  {BOLD}Path:{RESET}    {project.get('path', '?')}")
    print(f"  {BOLD}Branch:{RESET}  {project.get('default_branch', 'main')}")
    print()

    agents = project.get("agents", {})
    if agents:
        print(f"  {BOLD}Agents:{RESET}")
        base = os.path.basename(project.get("path", ""))
        parent = os.path.dirname(project.get("path", ""))
        for suffix, agent in agents.items():
            name = agent.get("name", suffix.title())
            sector = agent.get("sector") or "(cross-project)"
            worktree = f"{base}-{suffix}/"
            worktree_path = os.path.join(parent, f"{base}-{suffix}")
            exists = os.path.isdir(worktree_path)
            status = f"{GREEN}[ok]{RESET}" if exists else f"{RED}[missing]{RESET}"
            print(f"    {name:<14} {DIM}{sector:<20}{RESET} {worktree:<24} {status}")
        print()
    else:
        print(f"  No agents configured.\n")


# ──────────────────────────────────────────────────────────────
# Comms Commands (ported from comms.py)
# ──────────────────────────────────────────────────────────────


def cmd_post(args=""):
    """Send a message: /post SenderName message text"""
    if not args:
        print(f"  Usage: /post <sender> <message>")
        print(f'  Example: /post Web "please add GET /tasks/:id"')
        return

    parts = args.split(None, 1)
    if len(parts) < 2:
        print(f"  Usage: /post <sender> <message>")
        return

    sender = parts[0]
    message = parts[1].strip('"').strip("'")
    project_name = detect_current_project()[0] or "general"

    result = api_call(
        "POST",
        "/api/comms/messages",
        data={"sender": sender, "message": message, "channel": "general", "project": project_name},
    )
    if result:
        print(f"  {GREEN}Sent{RESET} as {BOLD}{sender}{RESET} -> [{project_name}]")
    else:
        print(f"  {RED}Failed to send message.{RESET}")


def _format_check_messages(result, prefix="  "):
    """Format and print check messages. Used by REPL, hook, and CLI dispatch."""
    agent_name = result.get("agentName", "?")
    cross = get_cross_project_agents()
    for msg in result["messages"]:
        ts = msg.get("timestamp", "")
        sender = msg.get("sender", "?")
        text = msg.get("message", "")
        msg_project = msg.get("project", "")
        time_str = parse_time(ts)
        directed = text.lower().startswith(agent_name.lower() + ":") or text.lower().startswith(
            agent_name.lower() + ","
        )
        tag = " >>> FOR YOU" if directed else ""
        proj_tag = f" [{msg_project}]" if agent_name in cross and msg_project else ""
        print(f"{prefix}{time_str}{proj_tag} {sender}: {text}{tag}")


def cmd_check(args=""):
    """Check unread messages for a session."""
    if not args:
        print(f"  Usage: /check <session_id>")
        return

    session_id = args.strip()
    result = api_call("GET", "/api/comms/check", params={"session_id": session_id}, fail_silent=True)

    if not result or not result.get("messages"):
        print(f"  No new messages.")
        return

    agent_name = result.get("agentName", "?")
    project = result.get("project", "?")

    print(f"  New messages (you are {BOLD}{agent_name}{RESET}, project={project}):")
    _format_check_messages(result)


def cmd_history(args=""):
    """Show recent messages."""
    limit = 20
    project_filter = None

    if args:
        for p in args.split():
            try:
                limit = int(p)
            except ValueError:
                project_filter = p

    params = {"limit": limit}
    if project_filter:
        params["project"] = project_filter
    else:
        pn = detect_current_project()[0]
        if pn:
            params["project"] = pn

    result = api_call("GET", "/api/comms/messages", params=params)
    if not result or not result.get("messages"):
        print(f"  No messages.")
        return

    print()
    for msg in result["messages"]:
        print(format_msg(msg))
    print()


def cmd_watch(_args=""):
    """Watch for new messages (polling)."""
    result = api_call("GET", "/api/comms/messages", params={"limit": 1})
    last_sk = None
    if result and result.get("messages"):
        last_sk = result["messages"][-1].get("sk")

    project_name = detect_current_project()[0]
    scope = f" [{project_name}]" if project_name else ""
    print(f"  {DIM}[watching{scope} — polling every 1.5s, Ctrl+C to stop]{RESET}")

    try:
        while True:
            params = {"limit": 50}
            if last_sk:
                params["after"] = last_sk
            if project_name:
                params["project"] = project_name
            result = api_call("GET", "/api/comms/messages", params=params, fail_silent=True)
            if result and result.get("messages"):
                for msg in result["messages"]:
                    print(format_msg(msg))
                    sk = msg.get("sk")
                    if sk:
                        last_sk = sk
            time.sleep(1.5)
    except KeyboardInterrupt:
        print(f"\n  {DIM}[stopped]{RESET}")


def cmd_chat(_args=""):
    """Interactive chat mode."""
    import select
    import termios
    import tty

    project_name = detect_current_project()[0] or "general"

    # Show recent messages for context
    result = api_call("GET", "/api/comms/messages", params={"limit": 10, "project": project_name})
    last_sk = None
    if result and result.get("messages"):
        for msg in result["messages"]:
            print(format_msg(msg))
            sk = msg.get("sk")
            if sk:
                last_sk = sk
        print()

    print(f"  {DIM}[chat mode — type message + enter to send, ctrl-c to quit]{RESET}")
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
                        api_call(
                            "POST",
                            "/api/comms/messages",
                            data={
                                "sender": "user",
                                "message": input_buf.strip(),
                                "channel": "general",
                                "project": project_name,
                            },
                        )
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
                    sys.stdout.write("\r" + " " * (len(input_buf) + 2) + "\r")
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
        print(f"\n  {DIM}[left chat]{RESET}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ──────────────────────────────────────────────────────────────
# Hook Handler (replaces comms.sh — non-interactive)
# ──────────────────────────────────────────────────────────────


def hook_handler(mode):
    """Handle Claude Code hook events. Called non-interactively via stdin JSON."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        input_data = {}

    session_id = input_data.get("session_id", "")
    if not session_id:
        return

    cwd = input_data.get("cwd", "")
    project = detect_project_for_hook(cwd)

    # Only managed projects participate in comms
    if project == "general":
        return

    if mode == "session-start":
        dir_name = os.path.basename(cwd)
        sender = auto_assign(session_id, cwd) or f"agent-{session_id[:8]}"
        api_call(
            "POST",
            "/api/comms/messages",
            data={
                "sender": sender,
                "message": f"Session started in {dir_name}",
                "channel": "general",
                "project": project,
            },
            fail_silent=True,
        )

    elif mode == "session-end":
        sender = resolve_name(session_id)
        api_call(
            "POST",
            "/api/comms/messages",
            data={
                "sender": sender,
                "message": "Session ended",
                "channel": "general",
                "project": project,
            },
            fail_silent=True,
        )

    elif mode == "check":
        result = api_call("GET", "/api/comms/check", params={"session_id": session_id}, fail_silent=True)
        if not result or not result.get("messages"):
            return

        agent_name = result.get("agentName", "?")
        project_name = result.get("project", "?")

        print(f"[comms] New messages (you are {agent_name}, project={project_name}):")
        _format_check_messages(result)

    elif mode == "git-detect":
        sender = resolve_name(session_id)
        tool_input = input_data.get("tool_input", {})
        cmd = tool_input.get("command", "")

        if re.search(r"\bgit\s+(checkout|switch|branch|merge|rebase|push|pull|worktree)\b", cmd):
            api_call(
                "POST",
                "/api/comms/messages",
                data={
                    "sender": sender,
                    "message": f"git: {cmd}",
                    "channel": "general",
                    "project": project,
                },
                fail_silent=True,
            )

        # Auto-pull main repo after gh pr merge
        if re.search(r"\bgh\s+pr\s+merge\b", cmd):
            try:
                wt = subprocess.run(
                    ["git", "worktree", "list", "--porcelain"],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=5,
                )
                if wt.returncode == 0:
                    lines = wt.stdout.strip().split("\n")
                    if lines:
                        main_repo = lines[0].replace("worktree ", "")
                        if os.path.isdir(main_repo):
                            br = subprocess.run(
                                ["git", "symbolic-ref", "--short", "HEAD"],
                                capture_output=True,
                                text=True,
                                cwd=main_repo,
                                timeout=5,
                            )
                            default_branch = br.stdout.strip() if br.returncode == 0 else ""
                            if default_branch:
                                subprocess.Popen(
                                    ["git", "pull", "origin", default_branch],
                                    cwd=main_repo,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                                api_call(
                                    "POST",
                                    "/api/comms/messages",
                                    data={
                                        "sender": sender,
                                        "message": f"auto-pulled {default_branch} in {os.path.basename(main_repo)}/",
                                        "channel": "general",
                                        "project": project,
                                    },
                                    fail_silent=True,
                                )
            except (subprocess.TimeoutExpired, OSError) as e:
                print(f"[comms] auto-pull failed: {e}", file=sys.stderr)


# ──────────────────────────────────────────────────────────────
# /install — One-time global setup
# ──────────────────────────────────────────────────────────────


def cmd_install(_args=""):
    """One-time global setup."""
    print()
    print(f"  {BOLD}Installing auto-agents...{RESET}")
    print()

    # Run doctor first
    cmd_doctor()

    # Find the setup directory (where this script lives)
    script_source = Path(__file__).resolve()
    setup_dir = script_source.parent

    # 1. Copy script to ~/.claude/scripts/
    print(f"  {BOLD}[1/4] Installing scripts...{RESET}")
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = SCRIPTS_DIR / "auto-agents.py"
    if script_source == dest:
        print(f"    {GREEN}[ok]{RESET} Already installed at {dest}")
    else:
        shutil.copy2(str(script_source), str(dest))
        print(f"    {GREEN}[ok]{RESET} Copied to {dest}")

    # Create the shell wrapper
    wrapper_dest = SCRIPTS_DIR / "auto-agents"
    wrapper_dest.write_text('#!/usr/bin/env bash\nexec python3 "$(dirname "$0")/auto-agents.py" "$@"\n')
    wrapper_dest.chmod(0o755)
    print(f"    {GREEN}[ok]{RESET} Created wrapper {wrapper_dest}")

    # Copy template so /init works from any directory
    template_src = setup_dir / "CLAUDE.md.template"
    template_dest = SCRIPTS_DIR / "CLAUDE.md.template"
    if template_src.exists():
        if template_src.resolve() == template_dest.resolve():
            print(f"    {GREEN}[ok]{RESET} CLAUDE.md.template already in place")
        else:
            shutil.copy2(str(template_src), str(template_dest))
            print(f"    {GREEN}[ok]{RESET} Copied CLAUDE.md.template")

    # Copy comms.py and comms.sh for backward compat
    for f in ["comms.py", "comms.sh"]:
        src = setup_dir / f
        dest_f = SCRIPTS_DIR / f
        if src.exists():
            if src.resolve() == dest_f.resolve():
                print(f"    {GREEN}[ok]{RESET} {f} already in place")
            else:
                shutil.copy2(str(src), str(dest_f))
                print(f"    {GREEN}[ok]{RESET} Copied {f} (backward compat)")

    # 2. Configure API credentials
    print()
    print(f"  {BOLD}[2/4] API configuration...{RESET}")
    if CONFIG_PATH.exists():
        print(f"    {GREEN}[ok]{RESET} Config already exists at {CONFIG_PATH}")
        reconfigure = input(f"    Reconfigure? [y/N]: ").strip().lower()
        if reconfigure != "y":
            print(f"    Skipped.")
        else:
            _prompt_api_config()
    else:
        _prompt_api_config()

    # 3. Install skills
    print()
    print(f"  {BOLD}[3/4] Installing skills...{RESET}")
    skills_source = setup_dir / "skills"
    # If not found locally, try auto-agents repo's setup/ dir via git
    if not (skills_source.exists() and skills_source.is_dir()):
        try:
            repo_result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5
            )
            if repo_result.returncode == 0:
                repo_skills = Path(repo_result.stdout.strip()) / "setup" / "skills"
                if repo_skills.exists() and repo_skills.is_dir():
                    skills_source = repo_skills
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    if skills_source.exists() and skills_source.is_dir():
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        for skill_dir in sorted(skills_source.iterdir()):
            if skill_dir.is_dir():
                dest_skill = SKILLS_DIR / skill_dir.name
                if dest_skill.exists():
                    shutil.rmtree(str(dest_skill))
                shutil.copytree(str(skill_dir), str(dest_skill))
                print(f"    {GREEN}[ok]{RESET} Installed skill: {skill_dir.name}")
    elif SKILLS_DIR.exists() and any(SKILLS_DIR.iterdir()):
        print(f"    {GREEN}[ok]{RESET} Skills already installed at {SKILLS_DIR}")
    else:
        print(f"    {YELLOW}[skip]{RESET} No skills/ directory found in {setup_dir}")

    # 4. PATH guidance
    print()
    print(f"  {BOLD}[4/4] PATH setup...{RESET}")
    if str(SCRIPTS_DIR) in os.environ.get("PATH", ""):
        print(f"    {GREEN}[ok]{RESET} {SCRIPTS_DIR} is already in PATH")
    else:
        shell = os.environ.get("SHELL", "/bin/bash")
        rc_file = "~/.zshrc" if "zsh" in shell else "~/.bashrc"
        print(f"    To add to PATH, run:")
        print(f'    {DIM}echo \'export PATH="$HOME/.claude/scripts:$PATH"\' >> {rc_file}{RESET}')
        print(f"    {DIM}source {rc_file}{RESET}")

    print()
    print(f"  {GREEN}{BOLD}Installation complete!{RESET}")
    print(f"  Run {BOLD}auto-agents{RESET} or {BOLD}/init{RESET} to set up a project.")
    print()


def _prompt_api_config():
    """Prompt for API credentials and save to config file."""
    COMMS_DIR.mkdir(parents=True, exist_ok=True)

    url = input(f"    Comms API URL: ").strip()
    if not url:
        print(f"    {YELLOW}Skipped{RESET} — set COMMS_API_URL later.")
        return

    secret = input(f"    API Secret: ").strip()

    CONFIG_PATH.write_text(f'COMMS_API_URL="{url}"\nCOMMS_API_SECRET="{secret}"\n')
    CONFIG_PATH.chmod(0o600)
    print(f"    {GREEN}[ok]{RESET} Saved to {CONFIG_PATH}")

    # Reset config cache
    global _config_cache
    _config_cache = None


# ──────────────────────────────────────────────────────────────
# /init — Set up a new project
# ──────────────────────────────────────────────────────────────


def _prompt_agents_manual(user_prefix=""):
    """Prompt user to define agents manually. Returns agents dict."""
    while True:
        agent_count_str = input(f"  How many agents? ").strip()
        try:
            agent_count = int(agent_count_str)
            if agent_count > 0:
                break
        except ValueError:
            pass
        print(f"  {RED}Please enter a positive number.{RESET}")

    agents = {}
    for i in range(1, agent_count + 1):
        print()
        print(f"  {BOLD}Agent {i}:{RESET}")

        suffix = input(f"    Suffix (short name, e.g. web, api, github): ").strip().lower()
        if not suffix:
            print(f"    {RED}Suffix required, skipping.{RESET}")
            continue

        base_name = suffix.title()
        default_name = f"{user_prefix.title()}_{base_name}" if user_prefix else base_name
        name = input(f"    Display name [{default_name}]: ").strip() or default_name

        cross_project = input(f"    Cross-project agent? [y/N]: ").strip().lower() == "y"
        sector = None if cross_project else input(f"    Sector directory (e.g. src/frontend/): ").strip()
        description = input(f"    Description: ").strip()

        agent_config = {"name": name, "description": description}
        if sector:
            agent_config["sector"] = sector
        if cross_project:
            agent_config["sector"] = None
            agent_config["cross_project"] = True

        agents[suffix] = agent_config
    return agents


def _is_autoagents_repo(path):
    """Check if a path looks like the auto-agents framework repo itself."""
    markers = ["setup/comms.py", "setup/comms.sh", "setup/setup-worktrees.sh", "sample-app"]
    return sum(1 for m in markers if os.path.exists(os.path.join(path, m))) >= 3


def _detect_directories(repo_dir):
    """Scan a project repo for top-level directories that could be agent sectors.

    Skips build artifacts, config dirs, and other non-sector directories.
    """
    skip = {
        # Version control & IDE
        ".git", ".github", ".gitlab", ".vscode", ".idea", ".fleet",
        # Claude / AI
        ".claude",
        # Build & output
        "node_modules", "dist", "build", "out", "target", ".next", ".nuxt",
        "__pycache__", ".cache", ".parcel-cache", ".turbo",
        "coverage", ".nyc_output", "htmlcov",
        # Virtual environments
        "venv", ".venv", "env", ".env", "virtualenv",
        # Dependencies
        "vendor", "bower_components", ".yarn",
        # Config & meta (not code sectors)
        "bin", "obj", "tmp", "temp", "logs", "log",
        # Common non-sector top-level dirs
        "scripts", "config", "configs", ".config",
        "docs", "doc", "documentation",
        "test", "tests", "__tests__", "spec", "specs",
        ".docker", "docker",
    }
    dirs = []
    for entry in sorted(os.listdir(repo_dir)):
        full = os.path.join(repo_dir, entry)
        if os.path.isdir(full) and entry not in skip and not entry.startswith("."):
            dirs.append(entry)
    return dirs


def _is_existing_worktree(path):
    """Check if a path is a worktree of an already-configured project.

    Returns (project_name, suffix) if it is, or (None, None) if not.
    """
    projects = load_projects().get("projects", {})
    base = os.path.basename(path)
    for pname, pconfig in projects.items():
        project_path = pconfig.get("path", "")
        if not project_path:
            continue
        repo_name = os.path.basename(project_path)
        for suffix in pconfig.get("agents", {}):
            if base == f"{repo_name}-{suffix}":
                return pname, suffix
    return None, None


def _create_worktree(repo_dir, worktree_dir, branch, default_branch):
    """Create a parking branch and worktree. Returns (ok, error_msg)."""
    try:
        result = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=repo_dir,
            timeout=5,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "branch", branch, default_branch], cwd=repo_dir, timeout=5, check=True
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return False, f"Failed to create branch {branch}: {e}"

    try:
        wt_result = subprocess.run(
            ["git", "worktree", "add", worktree_dir, branch],
            cwd=repo_dir,
            timeout=10,
            capture_output=True,
            text=True,
        )
        if wt_result.returncode == 0:
            return True, None
        err = wt_result.stderr.strip().split("\n")[0] if wt_result.stderr else "unknown error"
        return False, err
    except subprocess.TimeoutExpired:
        return False, "timed out"


def _build_sector_table(agents):
    """Build markdown sector table from agents dict."""
    sector_rows = []
    for suffix, agent in agents.items():
        name = agent.get("name", suffix.title())
        sector = agent.get("sector") or ""
        desc = agent.get("description", "")
        if agent.get("cross_project"):
            sector_rows.append(f"| {name} | (cross-project) | {name} | {desc} |")
        else:
            sector_rows.append(f"| {name} | `{sector or '/'}` | {name} | {desc} |")
    return (
        "| Sector | Directory | Agent | Responsibility |\n"
        "|--------|-----------|-------|----------------|\n" + "\n".join(sector_rows)
    )


def _render_claude_md(template, project_name, agent_name, sector, suffix, default_branch, sector_table):
    """Apply template substitutions and return rendered CLAUDE.md content."""
    content = template
    content = content.replace("{{PROJECT_NAME}}", project_name)
    content = content.replace("{{AGENT_NAME}}", agent_name)
    content = content.replace("{{SECTOR_DIR}}", sector or "(cross-project)")
    content = content.replace("{{AGENT_SUFFIX}}", suffix)
    content = content.replace("{{DEFAULT_BRANCH}}", default_branch)
    content = content.replace("{{SECTOR_TABLE}}", sector_table)
    return content


def _resolve_or_create_repo(prompt_text):
    """Prompt for a path, validate/create git repo. Returns repo_dir or None."""
    project_path = input(prompt_text).strip()
    if not project_path:
        return None
    project_path = os.path.expanduser(project_path)
    project_path = os.path.abspath(project_path)
    if os.path.isdir(project_path):
        check = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=project_path, timeout=5,
        )
        if check.returncode == 0:
            return check.stdout.strip()
        init_new = input(f"  Not a git repo. Initialize one? [Y/n]: ").strip().lower()
        if init_new != "n":
            subprocess.run(["git", "init"], cwd=project_path, timeout=5, check=True)
            return project_path
        return None
    else:
        create = input(f"  Directory doesn't exist. Create it? [Y/n]: ").strip().lower()
        if create != "n":
            os.makedirs(project_path, exist_ok=True)
            subprocess.run(["git", "init"], cwd=project_path, timeout=5, check=True)
            return project_path
        return None


def cmd_init(_args=""):
    """Interactive project setup wizard."""
    print()
    print(f"  {BOLD}Setting up auto-agents for a project...{RESET}")
    print()

    # Step 1: Find the target project repo
    repo_dir = None

    # Check if we're already in a git repo
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            detected_dir = result.stdout.strip()

            # Check if this is a worktree of an existing configured project
            wt_project, wt_suffix = _is_existing_worktree(detected_dir)
            if wt_project:
                print(f"  {YELLOW}Warning:{RESET} You're inside the '{wt_suffix}' worktree of project '{wt_project}'.")
                print(f"  To add/remove agents, use {BOLD}/add-agent{RESET} or {BOLD}/remove-agent{RESET}.")
                print(f"  To set up a different project, provide its path below.")
                print()
                repo_dir = _resolve_or_create_repo(f"  Enter a different project path (or Enter to cancel): ")
                if not repo_dir:
                    return

            # Warn if this is the auto-agents framework repo itself
            elif _is_autoagents_repo(detected_dir):
                print(f"  {YELLOW}Warning:{RESET} You're inside the auto-agents framework repo.")
                print(f"  This wizard sets up auto-agents for {BOLD}your project{RESET}, not for this repo.")
                print()
                repo_dir = _resolve_or_create_repo(f"  Enter the path to your project repo: ")
                if not repo_dir:
                    print(f"  {RED}No path provided. Cancelled.{RESET}")
                    return
            else:
                repo_dir = detected_dir
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # If not in a git repo at all, ask for a path
    if not repo_dir:
        print(f"  Not in a git repository.")
        print()
        repo_dir = _resolve_or_create_repo(f"  Enter the path to your project (existing or new): ")
        if not repo_dir:
            print(f"  {RED}No path provided. Cancelled.{RESET}")
            return

    repo_name = os.path.basename(repo_dir)
    parent_dir = os.path.dirname(repo_dir)

    print()
    print(f"  {GREEN}Project repo:{RESET} {CYAN}{repo_dir}{RESET}")

    # Check if already configured
    existing = load_projects().get("projects", {})
    for pname, pconfig in existing.items():
        if pconfig.get("path") == repo_dir:
            print(f"  {YELLOW}This project is already configured as '{pname}' "
                  f"with {len(pconfig.get('agents', {}))} agent(s).{RESET}")
            reconfigure = input(f"  Reconfigure from scratch? [y/N]: ").strip().lower()
            if reconfigure != "y":
                return
            break

    # Step 2: Project details
    print()
    project_name = input(f"  Project name [{repo_name}]: ").strip() or repo_name

    # Default branch
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, cwd=repo_dir, timeout=5,
        )
        current_branch = result.stdout.strip() if result.returncode == 0 else "main"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        current_branch = "main"

    default_branch = input(f"  Default branch [{current_branch}]: ").strip() or current_branch

    # Try to auto-detect GitHub remote
    gh_repo_default = ""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=repo_dir, timeout=5,
        )
        if result.returncode == 0:
            remote_url = result.stdout.strip()
            # Parse OWNER/REPO from git@github.com:OWNER/REPO.git or https://github.com/OWNER/REPO.git
            m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote_url)
            if m:
                gh_repo_default = m.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if gh_repo_default:
        gh_repo = input(f"  GitHub repo [{gh_repo_default}]: ").strip() or gh_repo_default
    else:
        gh_repo = input(f"  GitHub repo (OWNER/REPO, or Enter to skip): ").strip()

    # Step 3: Username prefix for agent identification
    print()
    os_user = os.environ.get("USER", os.environ.get("USERNAME", ""))
    user_prefix = input(f"  Your name/prefix for agent names [{os_user}]: ").strip() or os_user

    # Step 4: Agent setup — scan existing directories for suggestions
    print()
    detected_dirs = _detect_directories(repo_dir)
    agents = {}

    if detected_dirs:
        print(f"  {BOLD}Detected directories:{RESET} {', '.join(detected_dirs)}")
        print()
        use_detected = input(f"  Create an agent per directory? [Y/n]: ").strip().lower()
        if use_detected != "n":
            # Auto-create agents from detected directories
            for d in detected_dirs:
                suffix = d.lower().replace(" ", "-")
                default_name = f"{user_prefix.title()}_{suffix.title()}" if user_prefix else suffix.title()
                agents[suffix] = {
                    "name": default_name,
                    "sector": f"{d}/",
                    "description": f"Manages {d}/",
                }
                print(f"    {GREEN}+{RESET} {default_name:<20} -> {d}/")

            # Ask about a cross-project GitHub agent
            print()
            add_github = input(f"  Add a cross-project GitHub agent? [Y/n]: ").strip().lower()
            if add_github != "n":
                gh_name = f"{user_prefix.title()}_GitHub" if user_prefix else "GitHub"
                agents["github"] = {
                    "name": gh_name,
                    "sector": None,
                    "cross_project": True,
                    "description": "PR processing, CI, task coordination",
                }
                print(f"    {GREEN}+{RESET} {gh_name:<20} -> (cross-project)")

            # Allow customization
            print()
            customize = input(f"  Customize agent names/descriptions? [y/N]: ").strip().lower()
            if customize == "y":
                for suffix in list(agents.keys()):
                    agent = agents[suffix]
                    print()
                    print(f"  {BOLD}{agent['name']}:{RESET}")
                    new_name = input(f"    Display name [{agent['name']}]: ").strip()
                    if new_name:
                        agent["name"] = new_name
                    new_desc = input(f"    Description [{agent.get('description', '')}]: ").strip()
                    if new_desc:
                        agent["description"] = new_desc
        else:
            # Manual agent setup
            agents = _prompt_agents_manual(user_prefix)
    else:
        print(f"  {DIM}No subdirectories detected — entering manual agent setup.{RESET}")
        print()
        agents = _prompt_agents_manual(user_prefix)

    if not agents:
        print(f"  {RED}No agents defined. Cancelled.{RESET}")
        return

    # Confirm
    print()
    print(f"  {BOLD}Summary:{RESET}")
    print(f"    Project: {project_name}")
    print(f"    Path:    {repo_dir}")
    print(f"    Branch:  {default_branch}")
    if gh_repo:
        print(f"    Repo:    {gh_repo}")
    print(f"    Agents:")
    for suffix, a in agents.items():
        sector = a.get("sector") or "(cross-project)"
        print(f"      {a['name']:<14} {DIM}{sector}{RESET}")
    print()

    confirm = input(f"  Proceed? [Y/n]: ").strip().lower()
    if confirm == "n":
        print(f"  Cancelled.")
        return

    print()

    # Check if repo has at least one commit (worktrees need a commit to branch from)
    has_commits = _repo_has_commits(repo_dir)
    if not has_commits:
        print(f"  {YELLOW}Note:{RESET} Repo has no commits yet. Creating an initial commit...")
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "chore: initial commit"],
            cwd=repo_dir, capture_output=True, timeout=5,
        )
        has_commits = _repo_has_commits(repo_dir)
        if not has_commits:
            print(f"  {RED}Failed to create initial commit. Cannot create worktrees.{RESET}")
            return

    # Prune stale worktrees before creating new ones
    subprocess.run(["git", "worktree", "prune"], cwd=repo_dir, capture_output=True, timeout=5)

    # Create worktrees
    print(f"  {BOLD}Creating worktrees...{RESET}")
    for suffix in agents:
        worktree_dir = os.path.join(parent_dir, f"{repo_name}-{suffix}")
        branch = f"agent/{suffix}"

        if os.path.isdir(worktree_dir):
            print(f"    {YELLOW}[skip]{RESET} {os.path.basename(worktree_dir)}/ already exists")
            continue

        ok, err = _create_worktree(repo_dir, worktree_dir, branch, default_branch)
        if ok:
            print(f"    {GREEN}[ok]{RESET} {os.path.basename(worktree_dir)}/ -> {branch}")
        else:
            print(f"    {RED}[error]{RESET} {os.path.basename(worktree_dir)}/: {err}")

    # Generate .claude/settings.json in main repo AND each worktree
    # (Claude Code resolves settings relative to git root, which is the worktree dir for worktrees)
    print()
    print(f"  {BOLD}Generating .claude/settings.json...{RESET}")

    settings = _build_hook_settings()

    # Main repo
    _write_settings_json(repo_dir, settings)
    print(f"    {GREEN}[ok]{RESET} {repo_dir}/.claude/settings.json")

    # Each worktree
    for suffix in agents:
        worktree_dir = os.path.join(parent_dir, f"{repo_name}-{suffix}")
        if os.path.isdir(worktree_dir):
            _write_settings_json(worktree_dir, settings)
            print(f"    {GREEN}[ok]{RESET} {os.path.basename(worktree_dir)}/.claude/settings.json")

    # Generate CLAUDE.md from template
    print()
    print(f"  {BOLD}Generating CLAUDE.md...{RESET}")
    template = _load_template()

    if template:
        sector_table = _build_sector_table(agents)

        # Write per-worktree CLAUDE.md with agent-specific substitutions
        for suffix, agent in agents.items():
            worktree_dir = os.path.join(parent_dir, f"{repo_name}-{suffix}")
            if not os.path.isdir(worktree_dir):
                continue

            content = _render_claude_md(
                template, project_name, agent.get("name", suffix.title()),
                agent.get("sector"), suffix, default_branch, sector_table,
            )

            claude_md_path = os.path.join(worktree_dir, "CLAUDE.md")
            with open(claude_md_path, "w") as f:
                f.write(content)
            print(f"    {GREEN}[ok]{RESET} {os.path.basename(worktree_dir)}/CLAUDE.md")
    else:
        print(f"    {YELLOW}[skip]{RESET} CLAUDE.md.template not found. Run /install first or copy it manually.")

    # Create DECISIONS.md and CHECKPOINT.md
    print()
    for fname, header in [
        ("DECISIONS.md", "Track cross-agent architectural decisions here. All agents share this file.\n"),
        ("CHECKPOINT.md", "Crash recovery checkpoint. Write current task state here before complex work.\n"),
    ]:
        fpath = os.path.join(repo_dir, fname)
        if not os.path.exists(fpath):
            with open(fpath, "w") as f:
                f.write(f"# {fname.replace('.md', '')}\n\n{header}")
            print(f"  {GREEN}[ok]{RESET} Created {fname}")

    # Save to projects.json
    print()
    print(f"  {BOLD}Saving to projects.json...{RESET}")
    project_data = load_projects()
    project_data["projects"][project_name] = {
        "repo": gh_repo,
        "path": repo_dir,
        "default_branch": default_branch,
        "user_prefix": user_prefix,
        "agents": agents,
    }
    save_projects(project_data)
    print(f"    {GREEN}[ok]{RESET} Saved to {PROJECTS_PATH}")

    # Copilot review gate
    print()
    setup_gate = input(f"  Set up Copilot review gate? [Y/n]: ").strip().lower()
    if setup_gate != "n":
        workflow_source = _find_file("require-copilot-review.yml")
        if workflow_source:
            workflow_dir = os.path.join(repo_dir, ".github", "workflows")
            os.makedirs(workflow_dir, exist_ok=True)
            dest = os.path.join(workflow_dir, "require-copilot-review.yml")
            shutil.copy2(str(workflow_source), dest)
            print(f"    {GREEN}[ok]{RESET} Created {dest}")
        else:
            print(f"    {YELLOW}[skip]{RESET} require-copilot-review.yml not found")

    # Done — show next steps
    print()
    print(f"  {GREEN}{BOLD}Setup complete!{RESET}")
    print()
    print(f"  {BOLD}What was created:{RESET}")
    print(f"    - Git worktrees for each agent (sibling directories)")
    print(f"    - .claude/settings.json with hooks (project-local)")
    print(f"    - CLAUDE.md in each worktree (agent instructions)")
    print(f"    - DECISIONS.md + CHECKPOINT.md (shared memory)")
    print(f"    - Project registered in ~/.claude/comms/projects.json")
    print()
    print(f"  {BOLD}Next steps — launch each agent in a separate terminal:{RESET}")
    for suffix, agent in agents.items():
        name = agent.get("name", suffix.title())
        worktree_path = os.path.join(parent_dir, f"{repo_name}-{suffix}")
        print(f"    cd {worktree_path} && claude  {DIM}# {name}{RESET}")
    print()
    print(f"  {BOLD}Monitor the group chat:{RESET}")
    print(f"    cd {repo_dir} && auto-agents  {DIM}# then /watch or /chat{RESET}")
    print()
    print(f"  {BOLD}Give agents work:{RESET}")
    print(f"    In each agent terminal, describe what to build.")
    print(f"    Agents will coordinate via group chat automatically.")
    print()


def _repo_has_commits(repo_dir):
    """Check if a git repo has at least one commit."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir, capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _build_hook_settings():
    """Return the standard .claude/settings.json dict for hooks."""
    return {
        "env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80"},
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook session-start"}]}
            ],
            "Stop": [
                {"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook session-end"}]}
            ],
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook check"}]}
            ],
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook git-detect"}],
                }
            ],
        },
    }


def _write_settings_json(directory, settings):
    """Write .claude/settings.json into a directory."""
    claude_dir = os.path.join(directory, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    settings_path = os.path.join(claude_dir, "settings.json")
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")


def _find_file(name, search_scripts_dir=False):
    """Find a file in the setup directory, optionally installed scripts dir, or repo's setup/ dir."""
    p = Path(__file__).resolve().parent / name
    if p.exists():
        return p
    if search_scripts_dir:
        installed = SCRIPTS_DIR / name
        if installed.exists():
            return installed
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            fallback = Path(result.stdout.strip()) / "setup" / name
            if fallback.exists():
                return fallback
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _load_template():
    """Find and load CLAUDE.md.template."""
    p = _find_file("CLAUDE.md.template", search_scripts_dir=True)
    return p.read_text() if p else None


# ──────────────────────────────────────────────────────────────
# /add-agent and /remove-agent
# ──────────────────────────────────────────────────────────────


def cmd_add_agent(args=""):
    """Add an agent to the current project."""
    project_name, project = detect_current_project()
    if not project:
        print(f"  {RED}No project detected. Run /init first.{RESET}")
        return

    suffix = args.strip().lower() if args else input(f"  Agent suffix: ").strip().lower()
    if not suffix:
        print(f"  {RED}Suffix required.{RESET}")
        return

    if suffix in project.get("agents", {}):
        print(f"  {RED}Agent '{suffix}' already exists.{RESET}")
        return

    user_prefix = project.get("user_prefix", "")
    base_name = suffix.title()
    default_name = f"{user_prefix.title()}_{base_name}" if user_prefix else base_name
    name = input(f"  Display name [{default_name}]: ").strip() or default_name

    cross_project = input(f"  Cross-project? [y/N]: ").strip().lower() == "y"
    sector = None if cross_project else input(f"  Sector directory: ").strip()
    description = input(f"  Description: ").strip()

    repo_dir = project["path"]
    parent_dir = os.path.dirname(repo_dir)
    repo_name = os.path.basename(repo_dir)
    default_branch = project.get("default_branch", "main")

    # Create worktree
    worktree_dir = os.path.join(parent_dir, f"{repo_name}-{suffix}")
    branch = f"agent/{suffix}"

    # Ensure repo has commits
    if not _repo_has_commits(repo_dir):
        print(f"  {RED}Repo has no commits. Please commit something first.{RESET}")
        return

    # Prune stale worktrees first
    subprocess.run(["git", "worktree", "prune"], cwd=repo_dir, capture_output=True, timeout=5)

    if os.path.isdir(worktree_dir):
        print(f"  {YELLOW}[skip]{RESET} {worktree_dir} already exists")
    else:
        ok, err = _create_worktree(repo_dir, worktree_dir, branch, default_branch)
        if ok:
            print(f"  {GREEN}[created]{RESET} {os.path.basename(worktree_dir)}/ -> {branch}")
        else:
            print(f"  {RED}[error]{RESET} {err}")
            return

    # Update config
    agent_config = {"name": name, "description": description}
    if sector:
        agent_config["sector"] = sector
    if cross_project:
        agent_config["sector"] = None
        agent_config["cross_project"] = True

    data = load_projects()
    data["projects"][project_name]["agents"][suffix] = agent_config
    save_projects(data)
    print(f"  {GREEN}[ok]{RESET} Updated config.")

    # Create .claude/settings.json in the new worktree
    if os.path.isdir(worktree_dir):
        settings = _build_hook_settings()
        _write_settings_json(worktree_dir, settings)
        print(f"  {GREEN}[ok]{RESET} Created .claude/settings.json in worktree")

        # Generate CLAUDE.md for the new agent
        template = _load_template()
        if template:
            all_agents = data["projects"][project_name].get("agents", {})
            sector_table = _build_sector_table(all_agents)
            content = _render_claude_md(
                template, project_name, name, sector, suffix, default_branch, sector_table,
            )

            claude_md_path = os.path.join(worktree_dir, "CLAUDE.md")
            with open(claude_md_path, "w") as f:
                f.write(content)
            print(f"  {GREEN}[ok]{RESET} Created CLAUDE.md in worktree")
        else:
            print(f"  {YELLOW}[skip]{RESET} CLAUDE.md.template not found — no CLAUDE.md generated")

    # Notify chat
    api_call(
        "POST",
        "/api/comms/messages",
        data={
            "sender": "system",
            "message": f"New agent added: {name} ({suffix})",
            "channel": "general",
            "project": project_name,
        },
        fail_silent=True,
    )
    print(f"  {GREEN}[ok]{RESET} Posted notification to chat.")
    print()


def cmd_remove_agent(args=""):
    """Remove an agent from the current project."""
    project_name, project = detect_current_project()
    if not project:
        print(f"  {RED}No project detected. Run /init first.{RESET}")
        return

    agents = project.get("agents", {})
    suffix = args.strip().lower() if args else input(f"  Agent suffix to remove: ").strip().lower()
    if not suffix:
        print(f"  {RED}Suffix required.{RESET}")
        return

    if suffix not in agents:
        available = ", ".join(agents.keys())
        print(f"  {RED}Agent '{suffix}' not found. Available: {available}{RESET}")
        return

    agent = agents[suffix]
    name = agent.get("name", suffix.title())

    confirm = input(f"  Remove {BOLD}{name}{RESET} ({suffix})? [y/N]: ").strip().lower()
    if confirm != "y":
        print(f"  Cancelled.")
        return

    repo_dir = project["path"]
    parent_dir = os.path.dirname(repo_dir)
    repo_name = os.path.basename(repo_dir)
    worktree_dir = os.path.join(parent_dir, f"{repo_name}-{suffix}")

    # Remove worktree
    if os.path.isdir(worktree_dir):
        try:
            subprocess.run(
                ["git", "worktree", "remove", worktree_dir],
                cwd=repo_dir,
                timeout=10,
                check=True,
                capture_output=True,
            )
            print(f"  {GREEN}[removed]{RESET} {worktree_dir}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"  {YELLOW}[warning]{RESET} Could not remove worktree: {e}")
            print(f"  You may need to run: git worktree remove {worktree_dir} --force")

    # Update config
    data = load_projects()
    del data["projects"][project_name]["agents"][suffix]
    save_projects(data)
    print(f"  {GREEN}[ok]{RESET} Updated config.")

    # Notify chat
    api_call(
        "POST",
        "/api/comms/messages",
        data={
            "sender": "system",
            "message": f"Agent removed: {name} ({suffix})",
            "channel": "general",
            "project": project_name,
        },
        fail_silent=True,
    )
    print(f"  {GREEN}[ok]{RESET} Posted notification to chat.")
    print()


# ──────────────────────────────────────────────────────────────
# /menu — Re-show interactive menu from within REPL
# ──────────────────────────────────────────────────────────────


def cmd_menu(_args=""):
    """Show interactive setup menu."""
    if not sys.stdin.isatty():
        print(f"  Menu requires an interactive terminal.")
        return

    options = [
        ("Check environment", "/doctor", ""),
        ("Install auto-agents", "/install", ""),
        ("Set up a new project", "/init", ""),
        ("Add an agent", "/add-agent", ""),
        ("Remove an agent", "/remove-agent", ""),
        ("Back to REPL", "", ""),
    ]

    choice = interactive_menu("What would you like to do?", options)
    handlers = [cmd_doctor, cmd_install, cmd_init, cmd_add_agent, cmd_remove_agent, None]

    if 0 <= choice < len(handlers) and handlers[choice]:
        handlers[choice]()


# ──────────────────────────────────────────────────────────────
# Non-interactive dispatch (argparse)
# ──────────────────────────────────────────────────────────────


def dispatch_subcommand():
    """Handle non-interactive CLI usage via argparse."""
    parser = argparse.ArgumentParser(
        prog="auto-agents",
        description="auto-agents — unified CLI for multi-agent project setup and coordination",
    )
    sub = parser.add_subparsers(dest="command")

    # Hook handler
    p_hook = sub.add_parser("hook", help="Handle Claude Code hook events")
    p_hook.add_argument("mode", choices=["session-start", "session-end", "check", "git-detect"])

    # Setup commands
    sub.add_parser("doctor", help="Check prerequisites and environment")
    sub.add_parser("install", help="One-time global setup")
    sub.add_parser("init", help="Set up a new project")
    sub.add_parser("status", help="Show project config and agents")

    p_add = sub.add_parser("add-agent", help="Add an agent")
    p_add.add_argument("suffix", nargs="?", default="")

    p_rm = sub.add_parser("remove-agent", help="Remove an agent")
    p_rm.add_argument("suffix", nargs="?", default="")

    # Comms commands (backward-compatible with comms.py interface)
    p_post = sub.add_parser("post", help="Post a message")
    p_post.add_argument("-s", "--sender", default="user")
    p_post.add_argument("-c", "--channel", default="general")
    p_post.add_argument("-p", "--project", default=None)
    p_post.add_argument("message", nargs="+")

    p_history = sub.add_parser("history", help="Show recent messages")
    p_history.add_argument("n", nargs="?", type=int, default=20)
    p_history.add_argument("-p", "--project", default=None)

    sub.add_parser("watch", help="Watch for new messages")

    p_chat = sub.add_parser("chat", help="Interactive chat mode")
    p_chat.add_argument("-p", "--project", default=None)

    p_check = sub.add_parser("check", help="Get unread messages for a session")
    p_check.add_argument("session_id")

    p_resolve = sub.add_parser("resolve-name", help="Resolve session ID to name")
    p_resolve.add_argument("session_id")

    p_assign = sub.add_parser("assign", help="Assign a name to a session")
    p_assign.add_argument("name", nargs="?", default=None)
    p_assign.add_argument("agent_id", nargs="?", default=None)

    p_auto = sub.add_parser("auto-assign", help="Auto-assign name from directory")
    p_auto.add_argument("session_id")
    p_auto.add_argument("cwd")

    p_detect = sub.add_parser("detect-project", help="Detect project from directory")
    p_detect.add_argument("cwd")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "hook":
        hook_handler(args.mode)
    elif args.command == "doctor":
        cmd_doctor()
    elif args.command == "install":
        cmd_install()
    elif args.command == "init":
        cmd_init()
    elif args.command == "status":
        cmd_status()
    elif args.command == "add-agent":
        cmd_add_agent(args.suffix)
    elif args.command == "remove-agent":
        cmd_remove_agent(args.suffix)
    elif args.command == "post":
        message = " ".join(args.message)
        project = args.project or detect_project_for_hook(os.getcwd())
        cmd_post(f"{args.sender} {message}")
    elif args.command == "history":
        parts = [str(args.n)]
        if args.project:
            parts.append(args.project)
        cmd_history(" ".join(parts))
    elif args.command == "watch":
        cmd_watch()
    elif args.command == "chat":
        cmd_chat()
    elif args.command == "check":
        cmd_check(args.session_id)
    elif args.command == "resolve-name":
        print(resolve_name(args.session_id))
    elif args.command == "assign":
        _dispatch_assign(args)
    elif args.command == "auto-assign":
        name = auto_assign(args.session_id, args.cwd)
        print(name or "")
    elif args.command == "detect-project":
        print(detect_project_for_hook(args.cwd))


def _dispatch_assign(args):
    """Handle the 'assign' subcommand (non-interactive)."""
    if not args.name:
        result = api_call("GET", "/api/comms/agents")
        if result and result.get("agents"):
            print("Registered agents:")
            for a in result["agents"]:
                sid = a.get("sessionId", "?")[:12]
                proj = a.get("project", "?")
                print(f"  {a.get('name', '?'):<18} session={sid}  project={proj}")
        else:
            print("No agents registered.")
        return

    if not args.agent_id:
        print("Error: session_id required. Usage: auto-agents assign <name> <session_id>", file=sys.stderr)
        sys.exit(1)

    result = api_call("POST", "/api/comms/agents", data={"session_id": args.agent_id, "name": args.name})
    if result:
        print(f"Assigned: {args.agent_id} -> {result.get('name', args.name)}")


# ──────────────────────────────────────────────────────────────
# Command registry (populated after all definitions)
# ──────────────────────────────────────────────────────────────

COMMANDS.update(
    {
        "/help": cmd_help,
        "/doctor": cmd_doctor,
        "/install": cmd_install,
        "/init": cmd_init,
        "/add-agent": cmd_add_agent,
        "/remove-agent": cmd_remove_agent,
        "/status": cmd_status,
        "/post": cmd_post,
        "/check": cmd_check,
        "/watch": cmd_watch,
        "/chat": cmd_chat,
        "/history": cmd_history,
        "/menu": cmd_menu,
        "/exit": None,
    }
)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────


def main():
    # Non-interactive dispatch when called with args
    if len(sys.argv) > 1:
        dispatch_subcommand()
        return

    # Interactive mode — no args
    if not sys.stdin.isatty():
        print("Error: no command given. Usage: auto-agents <command> [args]", file=sys.stderr)
        print("Run 'auto-agents --help' for available commands.", file=sys.stderr)
        sys.exit(1)

    project_name, project = detect_current_project()

    if project:
        # Inside a configured project -> REPL
        repl(project_name)
    else:
        # Not in a project -> show setup menu
        options = [
            ("Check environment", "/doctor", ""),
            ("Install auto-agents", "/install", ""),
            ("Set up a new project", "/init", ""),
            ("Exit", "/exit", ""),
        ]

        choice = interactive_menu("What would you like to do?", options)
        handlers = [cmd_doctor, cmd_install, cmd_init, None]

        if 0 <= choice < len(handlers) and handlers[choice]:
            handlers[choice]()

            # After setup action, check if we're now in a project
            project_name, project = detect_current_project()
            if project:
                repl(project_name)
            else:
                # Project was likely set up in a different directory
                projects = load_projects().get("projects", {})
                if projects:
                    print(f"  {DIM}Tip: run {BOLD}auto-agents{RESET}{DIM} from your project directory to enter the REPL.{RESET}")
                    print()


if __name__ == "__main__":
    main()
