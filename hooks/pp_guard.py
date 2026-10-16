"""PreToolUse guard for persona-panel's own subagents (stdlib only).

Claude Code runs this before every tool call when the plugin is enabled (hooks/hooks.json,
through pp_guard.sh). It reads the hook input JSON on stdin and only acts when `agent_type`
is one of persona-panel's agents, as a plugin agent (`persona-panel:pp-walker`) or a manual
copy in ~/.claude/agents (`pp-walker`). Every other agent and the main session get no output,
so their calls go through Claude Code's normal permission flow untouched.

For pp-* agents it allows only:
  Read      files under the configured runs_dir, and this skill's references/ folder
  Write     pp-panelist:    <runs_dir>/.../results/*.json
  Edit      pp-walker:      the same, plus anything under <runs_dir>/.../walk/
            pp-synthesizer: <runs_dir>/.../synthesis.json
  Bash      pp-walker only: one `"PY" ".../walk.py" "<runs_dir>/.../walk/<pid>" <verb> [args]` call,
  PowerShell  with no ; & | ` $ < > or line breaks, and only quoted strings or plain words
            (a PowerShell command may start with `& `)
and denies everything else with a reason. It exits 0 and prints a deny decision as JSON;
if anything goes wrong while checking a pp-* call, it denies.
"""
import sys

sys.dont_write_bytecode = True  # the plugin folder is read-only

import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent / "skills" / "persona-panel"
SCRIPTS = SKILL_DIR / "scripts"
REFERENCES = SKILL_DIR / "references"
WALK_PY = SCRIPTS / "walk.py"

AGENT_RE = re.compile(r"^(?:persona-panel:)?pp-(panelist|walker|synthesizer)$")
WALK_VERBS = {"start", "look", "click", "click-text", "type", "select", "press", "scroll", "back", "goto", "stop"}
PYTHON_NAME = re.compile(r"^(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?$", re.I)
# Characters that let a shell do more than run one program: chaining, pipes, substitution, redirects.
# (Comments, globs and ~ could only start a bare word, and bare words may not contain them: see TOKEN.)
SHELL_META = re.compile(r"[;&|`$<>\r\n\x00]")
TOKEN = re.compile(r"""\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_./:+=-]+))(?=\s|$)""")
FILE_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}


def _norm(p):
    return Path(os.path.normcase(str(Path(p).expanduser().resolve())))


def inside(path, root):
    try:
        return _norm(path).is_relative_to(_norm(root))
    except (OSError, ValueError, TypeError):
        return False


def runs_root(cwd):
    """The configured runs folder, read the same way the scripts read it (paths.py), from the session's cwd."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import paths
    return Path(paths.load_config(cwd=cwd or None)["runs_dir"])


def deny(role, reason):
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"persona-panel guard ({role}): {reason}",
    }}


def tokenize(command):
    """Shell words of a command made only of quoted strings and plain words, or None if it has anything else."""
    tokens, pos = [], 0
    while pos < len(command):
        if not command[pos:].strip():
            break
        m = TOKEN.match(command, pos)
        if not m:
            return None
        dq, sq, bare = m.groups()
        if dq is not None and dq.endswith("\\"):
            return None  # bash would read \" as a literal quote and keep the string going
        tokens.append(dq if dq is not None else sq if sq is not None else bare)
        pos = m.end()
    return tokens


def same_walk_py(path):
    """The token names this plugin's walk.py, or an identical copy (another install of the same version)."""
    try:
        p = Path(path).expanduser().resolve()
        if _norm(p) == _norm(WALK_PY):
            return True
        return p.name == "walk.py" and p.is_file() and p.read_bytes() == WALK_PY.read_bytes()
    except OSError:
        return False


def check_walk_command(command, tool, root):
    """None if `command` is a single allowed walk.py call, else the reason it isn't."""
    if not isinstance(command, str) or not command.strip():
        return "empty command"
    cmd = command.strip()
    if tool == "PowerShell" and cmd.startswith("& "):
        cmd = cmd[2:].strip()
    if SHELL_META.search(cmd):
        return "only a single walk.py command is allowed: no ; & | ` $ < > or line breaks"
    tokens = tokenize(cmd)
    if not tokens or len(tokens) < 4:
        return "expected: \"PY\" \".../walk.py\" \"<run>/walk/<pid>\" <command> [args], with arguments in quotes"
    py, walk, session, verb = tokens[:4]
    if not PYTHON_NAME.match(Path(py).name) or (("/" in py or "\\" in py) and (inside(py, root) or not Path(py).is_file())):
        return f"the first word must be a Python interpreter, not {py[:80]!r}"
    if inside(walk, root) or not same_walk_py(walk):
        return f"only persona-panel's walk.py may be run, not {walk[:80]!r}"
    if not inside(session, root) or Path(session).parent.name != "walk":
        return "the walk session folder must be <run>/walk/<pid> inside the runs folder"
    if verb not in WALK_VERBS:
        return f"unknown walk.py command {verb!r}"
    return None


def check_write(role, path, root):
    p = Path(path).expanduser().resolve()
    if not inside(p, root):
        return f"may only write inside the runs folder ({root}), not {path}"
    if p.parent.name == "results" and p.suffix.lower() == ".json" and role in ("panelist", "walker"):
        return None
    if role == "walker" and "walk" in _norm(p).relative_to(_norm(root)).parts[:-1]:
        return None
    if role == "synthesizer" and p.name == "synthesis.json":
        return None
    allowed = {"panelist": "results/*.json", "walker": "results/*.json or its walk/ folder",
               "synthesizer": "synthesis.json"}[role]
    return f"may only write {allowed} in the run folder, not {path}"


def decide(event):
    """The hook output for one PreToolUse event, or None to let the call through untouched."""
    if not isinstance(event, dict):
        return None
    m = AGENT_RE.match(str(event.get("agent_type") or ""))
    if not m:
        return None
    role = m.group(1)
    agent = f"pp-{role}"
    try:
        tool = event.get("tool_name")
        args = event.get("tool_input") or {}
        root = runs_root(event.get("cwd"))
        if tool in SHELL_TOOLS:
            if role != "walker":
                return deny(agent, f"{tool} is not allowed for this agent")
            reason = check_walk_command(args.get("command"), tool, root)
            return deny(agent, reason) if reason else None
        if tool in FILE_TOOLS:
            path = args.get("file_path") or args.get("notebook_path")
            if not isinstance(path, str) or not path:
                return deny(agent, f"{tool} without a file path")
            if tool == "NotebookEdit":
                return deny(agent, "NotebookEdit is not allowed for this agent")
            if tool == "Read":
                if inside(path, root) or inside(path, REFERENCES):
                    return None
                return deny(agent, f"may only read files in the runs folder ({root}) or the skill's references, not {path}")
            reason = check_write(role, path, root)
            return deny(agent, reason) if reason else None
        return deny(agent, f"{tool} is not allowed for this agent")
    except Exception as e:  # never let a pp agent through because the check itself failed
        return deny(agent, f"could not check this call ({type(e).__name__}: {str(e)[:120]})")


def main():
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else None
    except (ValueError, OSError):
        return 0
    out = decide(event)
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
