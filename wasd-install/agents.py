#!/usr/bin/env python3
"""Install the agents chosen in Install WASD.

Web apps open in their own Brave window, the same kind of window Omarchy
makes. Command-line agents with a checked installer are downloaded on first
boot. The others get a menu entry and are not downloaded. Sign-in stays on
the person's own account. Nothing here is a WASD-hosted model.

The self-check injects the command runner. It does not download anything.
"""

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

WEBAPP = "/usr/libexec/wasd-webapp"


class AgentError(Exception):
    pass


class Agent:
    def __init__(self, agent_id, kind, url="", binary="", stamp="", bins=()):
        self.agent_id = agent_id
        self.kind = kind
        self.url = url
        self.binary = binary
        self.stamp = stamp
        self.bins = tuple(bins) if bins else ((binary,) if binary else ())

    def fetches(self):
        return self.kind == "cli" and bool(self.url)


# Display names match Install WASD. Install URLs are the official scripts
# that were checked. A name with no URL is a menu entry only.
CATALOG = {
    "Grok Build": Agent("grok-build", "cli", "https://x.ai/cli/install.sh", "grok", "grok"),
    "Grok Bot": Agent("grok-bot", "cli", "https://x.ai/cli/install.sh", "grok", "grok"),
    "Grok": Agent("grok", "web", "https://grok.com/"),
    "Claude Code": Agent("claude-code", "cli", "https://claude.ai/install.sh", "claude", "claude"),
    "Codex": Agent("codex", "cli"),
    "OpenCode": Agent("opencode", "cli", "https://opencode.ai/install", "opencode", "opencode"),
    "Antigravity": Agent("antigravity", "cli"),
    "Amp": Agent("amp", "cli", "https://ampcode.com/install.sh", "amp", "amp"),
    "Command Code": Agent("command-code", "cli"),
    "Copilot CLI": Agent("copilot", "cli"),
    "Crush": Agent("crush", "cli"),
    "Cursor CLI": Agent("cursor", "cli", "https://cursor.com/install", "cursor-agent", "cursor", ("cursor-agent", "agent")),
    "Devin": Agent("devin", "cli"),
    "DeepSeek Harness": Agent("deepseek", "cli"),
    "Freebuff": Agent("freebuff", "cli"),
    "Hermes": Agent("hermes", "cli"),
    "Kilo": Agent("kilo", "cli"),
    "Kimi": Agent("kimi", "cli"),
    "Kiro": Agent("kiro", "cli"),
    "MiniMax Code": Agent("minimax", "cli"),
    "Muse": Agent("muse", "cli"),
    "Oh My Pi": Agent("oh-my-pi", "cli"),
    "Ori": Agent("ori", "cli"),
    "Pi": Agent("pi", "cli"),
    "Qwen": Agent("qwen", "cli"),
    "ChatGPT": Agent("chatgpt", "web", "https://chatgpt.com/"),
    "Claude": Agent("claude", "web", "https://claude.ai/"),
    "Hermes Desktop": Agent("hermes-desktop", "cli"),
    "OpenClaw": Agent("openclaw", "cli"),
    "Perplexity": Agent("perplexity", "web", "https://www.perplexity.ai/"),
    "T3 Code": Agent("t3-code", "cli"),
    "LM Studio": Agent("lm-studio", "cli"),
    "Ollama": Agent("ollama", "cli", "https://ollama.com/install.sh", "ollama", "ollama"),
}


def names_from(data):
    """Return the agent list, or None when the installer did not save one."""
    if not isinstance(data, dict) or "agents" not in data:
        return None
    raw = data["agents"]
    if not isinstance(raw, list):
        raise AgentError("Choose the agents again.")
    names = []
    for item in raw:
        if not isinstance(item, str) or item not in CATALOG or item in names:
            raise AgentError("Choose the agents again.")
        names.append(item)
    return names


def agents_problem(data):
    try:
        names_from(data)
    except AgentError:
        return "Choose the agents again. Nothing was erased."
    return ""


def needs_fetch(name):
    return CATALOG[name].fetches()


def _stamp(home, agent):
    if not agent.stamp:
        return None
    return home / ".local/share/wasd/agents" / agent.stamp


def _wrapper(agent):
    if agent.kind == "web":
        return ""
    lines = ["#!/bin/bash", "set -euo pipefail"]
    if agent.fetches():
        quoted = " ".join(shlex.quote(item) for item in agent.bins)
        lines.extend(
            [
                f"bins=({quoted})",
                "found=",
                'for bin in "${bins[@]}"; do',
                '    if command -v "$bin" >/dev/null 2>&1; then',
                '        found=$(command -v "$bin")',
                "        break",
                "    fi",
                '    if [[ -x "$HOME/.local/bin/$bin" ]]; then',
                '        found="$HOME/.local/bin/$bin"',
                "        break",
                "    fi",
                "done",
                'if [[ -z $found ]]; then',
                "    tmp=$(mktemp)",
                f"    curl -fsSL --output \"$tmp\" {shlex.quote(agent.url)}",
                '    bash "$tmp"',
                '    rm -f "$tmp"',
                '    for bin in "${bins[@]}"; do',
                '        if command -v "$bin" >/dev/null 2>&1; then',
                '            found=$(command -v "$bin")',
                "            break",
                "        fi",
                '        if [[ -x "$HOME/.local/bin/$bin" ]]; then',
                '            found="$HOME/.local/bin/$bin"',
                "            break",
                "        fi",
                "    done",
                "fi",
                'if [[ -z $found ]]; then',
                '    echo "This agent did not finish installing." >&2',
                "    exit 1",
                "fi",
                'exec "$found" "$@"',
            ]
        )
    else:
        lines.extend(
            [
                'echo "This one is on the menu. WASD does not download it. Install it with your own account when you want it."',
                'exec "${SHELL:-/bin/bash}"',
            ]
        )
    return "\n".join(lines) + "\n"


def _desktop(home, agent, title):
    if agent.kind == "web":
        command = f"{WEBAPP} {agent.url}"
        terminal = "false"
    else:
        command = f"konsole --hide-menubar -e {home / '.local/bin' / ('wasd-agent-' + agent.agent_id)}"
        terminal = "false"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={title}\n"
        f"Exec={command}\n"
        "Icon=wasd-logo\n"
        f"Terminal={terminal}\n"
        "Categories=Development;\n"
    )


def write_launcher(home, name):
    agent = CATALOG[name]
    home = Path(home)
    desktop = home / ".local/share/applications" / f"wasd-agent-{agent.agent_id}.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(_desktop(home, agent, name), encoding="utf-8")
    os.chmod(desktop, 0o644)
    if agent.kind == "web":
        return desktop
    wrapper = home / ".local/bin" / f"wasd-agent-{agent.agent_id}"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(_wrapper(agent), encoding="utf-8")
    os.chmod(wrapper, 0o755)
    return desktop


def prepare(home, names):
    for name in names:
        write_launcher(home, name)


def _run(runner, argv):
    try:
        result = runner(argv)
    except AgentError:
        raise
    except Exception as exc:
        raise AgentError("Could not install that agent.") from exc
    if not isinstance(result, tuple) or len(result) != 3:
        raise AgentError("Could not install that agent.")
    code, out, err = result
    if not isinstance(code, int):
        raise AgentError("Could not install that agent.")
    return code, out or b"", err or b""


def install_agent(home, name, runner):
    agent = CATALOG[name]
    home = Path(home)
    write_launcher(home, name)
    if not agent.fetches():
        return
    stamp = _stamp(home, agent)
    if stamp is not None and stamp.is_file():
        return
    for binary in agent.bins:
        if (home / ".local/bin" / binary).is_file():
            if stamp is not None:
                stamp.parent.mkdir(parents=True, exist_ok=True)
                stamp.write_text("ok\n", encoding="utf-8")
            return
    handle = tempfile.NamedTemporaryFile(prefix="wasd-agent-", delete=False)
    dest = Path(handle.name)
    handle.close()
    try:
        code, _out, _err = _run(runner, ["curl", "-fsSL", "--output", str(dest), agent.url])
        if code != 0:
            raise AgentError("Could not install that agent.")
        try:
            body = dest.read_bytes()
        except OSError as exc:
            raise AgentError("Could not install that agent.") from exc
        if not body.startswith(b"#!"):
            raise AgentError("Could not install that agent.")
        code, _out, _err = _run(runner, ["bash", str(dest)])
        if code != 0:
            raise AgentError("Could not install that agent.")
    finally:
        dest.unlink(missing_ok=True)
    if stamp is not None:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text("ok\n", encoding="utf-8")
        os.chmod(stamp, 0o644)


def real_runner(argv):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to install an agent")
    proc = subprocess.run(argv, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def marker_path():
    return Path(os.environ.get("WASD_AGENTS_MARK", "/etc/wasd/agents-set"))


def write_marker():
    path = marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok\n", encoding="utf-8")
    os.chmod(path, 0o644)


def self_check():
    import tempfile

    os.environ["WASD_SELF_CHECK"] = "1"
    calls = []

    def runner(argv):
        calls.append(list(argv))
        if argv[0] == "curl":
            Path(argv[argv.index("--output") + 1]).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            return 0, b"", b""
        if argv[0] == "bash":
            if not getattr(runner, "failed", False):
                runner.failed = True
                return 1, b"", b"no"
            return 0, b"", b""
        return 1, b"", b"no"

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        names = ["Grok Build", "Grok Bot", "Grok", "Codex"]
        prepare(home, names)
        try:
            install_agent(home, "Grok Build", runner)
        except AgentError:
            pass
        else:
            raise SystemExit("a failed installer was treated as installed")
        if (home / ".local/share/wasd/agents/grok").exists():
            raise SystemExit("a failed installer left a stamp")
        install_agent(home, "Grok Build", runner)
        install_agent(home, "Grok Bot", runner)
        install_agent(home, "Grok", runner)
        install_agent(home, "Codex", runner)
        curls = [item for item in calls if item[0] == "curl"]
        if len(curls) != 2 or curls[0][-1] != "https://x.ai/cli/install.sh":
            raise SystemExit(f"the grok installer was not run once and retried: {curls}")
        if any("codex" in item[-1] for item in curls):
            raise SystemExit("an unverified agent was downloaded")
        web = (home / ".local/share/applications/wasd-agent-grok.desktop").read_text(encoding="utf-8")
        if f"Exec={WEBAPP} https://grok.com/" not in web:
            raise SystemExit("the Grok window was not created")
        bot = (home / ".local/share/applications/wasd-agent-grok-bot.desktop").read_text(encoding="utf-8")
        if "wasd-agent-grok-bot" not in bot or "Name=Grok Bot" not in bot:
            raise SystemExit("Grok Bot was not its own menu entry")
        codex = (home / ".local/bin/wasd-agent-codex").read_text(encoding="utf-8")
        if "does not download" not in codex or "curl" in codex:
            raise SystemExit("an unverified agent got an installer")
        chat = _desktop(home, CATALOG["ChatGPT"], "ChatGPT")
        if "https://chatgpt.com/" not in chat:
            raise SystemExit("ChatGPT was not a web app")
        try:
            names_from({"agents": ["Nope"]})
        except AgentError:
            pass
        else:
            raise SystemExit("an unknown agent was accepted")
        try:
            names_from({"agents": ["Grok", "Grok"]})
        except AgentError:
            pass
        else:
            raise SystemExit("a repeated agent was accepted")
        if names_from({"password": False}) is not None:
            raise SystemExit("a missing agent list was treated as a choice")
        os.environ["WASD_AGENTS_MARK"] = str(Path(tmp) / "agents-set")
        write_marker()
        if Path(os.environ["WASD_AGENTS_MARK"]).read_text(encoding="utf-8") != "ok\n":
            raise SystemExit("the agent marker was not written")
    print("agents self-check ok")


def main(argv):
    if "--self-check" in argv:
        self_check()
        return 0
    if argv == ["--mark"]:
        if os.environ.get("WASD_SELF_CHECK") == "1":
            print("self-check tried to mark the agents", file=sys.stderr)
            return 2
        write_marker()
        return 0
    print("This is only used by Completing the install.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
