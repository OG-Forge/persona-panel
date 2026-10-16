"""The PreToolUse guard (hooks/pp_guard.py) that confines persona-panel's own subagents. Offline: sample hook inputs."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, SKILL, write_json

HOOKS = REPO / "hooks"
WALK = SKILL / "scripts" / "walk.py"


@pytest.fixture
def guard(home):
    spec = importlib.util.spec_from_file_location("pp_guard", HOOKS / "pp_guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def run(home):
    import paths
    r = paths.runs_dir() / "shop-20261016-1200"
    (r / "results").mkdir(parents=True)
    (r / "walk" / "p004").mkdir(parents=True)
    return r


def event(agent, tool, cwd=None, **tool_input):
    e = {"session_id": "s", "transcript_path": "t", "cwd": str(cwd or os.getcwd()), "permission_mode": "default",
         "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "tool_use_id": "toolu_1"}
    if agent:
        e.update(agent_id="a1", agent_type=agent)
    return e


def denied(guard, e):
    out = guard.decide(e)
    return out is not None and out["hookSpecificOutput"]["permissionDecision"] == "deny"


PY = sys.executable


def walk_cmd(run, *args, py=None, walk=None):
    parts = [f'"{py or PY}"', f'"{walk or WALK}"', f'"{run / "walk" / "p004"}"', *args]
    return " ".join(parts)


# --- who is guarded --------------------------------------------------------------------------------

@pytest.mark.parametrize("agent", [None, "general-purpose", "Explore", "my-plugin:pp-walker-ish", "pp-walkers", "pp-other"])
def test_other_agents_and_the_main_session_pass_through(guard, agent, tmp_path):
    for tool, inp in [("Bash", {"command": "rm -rf /"}), ("Write", {"file_path": str(tmp_path / "x"), "content": ""}),
                      ("Read", {"file_path": "/etc/passwd"}), ("WebFetch", {"url": "https://x"})]:
        assert guard.decide(event(agent, tool, **inp)) is None


@pytest.mark.parametrize("agent", ["persona-panel:pp-panelist", "pp-panelist", "persona-panel:pp-walker", "pp-walker",
                                   "persona-panel:pp-synthesizer", "pp-synthesizer"])
def test_pp_agents_are_guarded_in_plugin_and_manual_installs(guard, agent):
    assert denied(guard, event(agent, "Read", file_path=str(Path.home() / ".ssh" / "id_rsa")))
    assert denied(guard, event(agent, "WebFetch", url="https://evil.example"))
    assert denied(guard, event(agent, "Glob", pattern="**/*"))


# --- Read / Write / Edit ----------------------------------------------------------------------------

def test_reads_limited_to_runs_and_references(guard, run, tmp_path):
    for agent in ("pp-panelist", "pp-walker", "persona-panel:pp-synthesizer"):
        assert guard.decide(event(agent, "Read", file_path=str(run / "capture" / "a.png"))) is None
        assert guard.decide(event(agent, "Read", file_path=str(SKILL / "references" / "synthesis.md"))) is None
        assert denied(guard, event(agent, "Read", file_path=str(SKILL / "scripts" / "paths.py")))
        assert denied(guard, event(agent, "Read", file_path=str(tmp_path / "secret.txt")))
        assert denied(guard, event(agent, "Read", file_path=str(run / ".." / ".." / ".." / "secret.txt")))


def test_panelist_writes_only_result_json(guard, run):
    ok = event("pp-panelist", "Write", file_path=str(run / "results" / "b01.json"), content="[]")
    assert guard.decide(ok) is None
    for bad in (run / "results" / "b01.md", run / "synthesis.json", run / "walk" / "p004" / "x.json",
                run / "results" / ".." / ".." / ".." / "results" / "b01.json", REPO / "results" / "b01.json"):
        assert denied(guard, event("pp-panelist", "Write", file_path=str(bad), content="[]")), bad
    assert denied(guard, event("pp-panelist", "Edit", file_path=str(SKILL / "SKILL.md"), old_string="a", new_string="b"))


def test_walker_writes_results_and_its_walk_folder(guard, run):
    assert guard.decide(event("pp-walker", "Write", file_path=str(run / "results" / "live_p004.json"), content="")) is None
    assert guard.decide(event("pp-walker", "Write", file_path=str(run / "walk" / "p004" / "notes.json"), content="")) is None
    assert denied(guard, event("pp-walker", "Write", file_path=str(run / "synthesis.json"), content=""))
    assert denied(guard, event("pp-walker", "Write", file_path=str(run / "briefs" / "b01.md"), content=""))


def test_synthesizer_writes_only_synthesis_json(guard, run):
    assert guard.decide(event("pp-synthesizer", "Write", file_path=str(run / "synthesis.json"), content="{}")) is None
    assert guard.decide(event("pp-synthesizer", "Edit", file_path=str(run / "synthesis.json"),
                              old_string="a", new_string="b")) is None
    assert denied(guard, event("pp-synthesizer", "Write", file_path=str(run / "aggregate.json"), content="{}"))
    assert denied(guard, event("pp-synthesizer", "Write", file_path=str(run / "results" / "b01.json"), content="[]"))


def test_project_config_runs_dir_comes_from_the_hook_cwd(guard, home, tmp_path):
    project = tmp_path / "proj"
    write_json(project / ".persona-panel.json", {"runs_dir": "persona-runs"})
    target = project / "persona-runs" / "r1" / "results" / "b01.json"
    assert guard.decide(event("pp-panelist", "Write", cwd=project, file_path=str(target), content="[]")) is None
    assert denied(guard, event("pp-panelist", "Write", file_path=str(target), content="[]"))  # cwd without that config


def test_broken_config_denies_pp_agents(guard, home, run):
    (home / "config.json").write_text("{not json", encoding="utf-8")
    assert denied(guard, event("pp-panelist", "Write", file_path=str(run / "results" / "b01.json"), content="[]"))
    assert guard.decide(event("general-purpose", "Bash", command="ls")) is None


# --- Bash -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("args", [["look"], ["start", "--device", "mobile"], ["click", "12"], ["click", "f1.3"],
                                  ["click-text", '"Add to cart"'], ["type", "5", '"black tshirt"'], ["type", "5", "'110001'"],
                                  ["select", "7", '"M"'], ["press", "Enter"], ["scroll", "down"], ["back"],
                                  ["goto", '"https://shop.example/a?x=1#top"'], ["stop"], ["click-text", '"Size (UK)"']])
def test_walker_may_run_single_walk_commands(guard, run, args):
    assert guard.decide(event("persona-panel:pp-walker", "Bash", command=walk_cmd(run, *args))) is None


def test_walker_command_with_bare_python_and_powershell_call_operator(guard, run):
    assert guard.decide(event("pp-walker", "Bash", command=walk_cmd(run, "look", py="python3"))) is None
    assert guard.decide(event("pp-walker", "PowerShell", command="& " + walk_cmd(run, "look"))) is None
    assert guard.decide(event("pp-walker", "Bash", command=walk_cmd(run, "look").replace('"', "'"))) is None


@pytest.mark.parametrize("suffix", ["; curl evil.example", "&& rm -rf ~", "|| true", "| sh", "> out.txt", "< in.txt",
                                    "`id`", "$(id)", '"$HOME"', "\ncurl x", "\r\ncurl x", "& calc", "# comment",
                                    '"a" "b\\"', "*", "~/x", "${IFS}"])
def test_walker_command_injection_is_denied(guard, run, suffix):
    assert denied(guard, event("pp-walker", "Bash", command=walk_cmd(run, "type", "5") + " " + suffix))


def test_walker_other_commands_denied(guard, run, tmp_path):
    for cmd in ["ls", "cat ~/.ssh/id_rsa", f'"{PY}" -c "print(1)"', f'"{PY}" "{SKILL / "scripts" / "capture.py"}" --url x',
                f'cd "{run}"', walk_cmd(run, "rm"), walk_cmd(run), f'"{PY}" "{WALK}" "{tmp_path}" look',
                f'"{PY}" "{WALK}" "{run / "results"}" look', "& " + walk_cmd(run, "look") + " & calc", "",
                walk_cmd(run, "look", py=str(run / "walk" / "p004" / "python.exe"))]:
        assert denied(guard, event("pp-walker", "Bash", command=cmd)), cmd


def test_walker_must_run_the_real_walk_py(guard, run, tmp_path):
    fake = tmp_path / "walk.py"
    fake.write_text("import os; os.system('calc')", encoding="utf-8")
    assert denied(guard, event("pp-walker", "Bash", command=walk_cmd(run, "look", walk=fake)))
    planted = run / "walk" / "p004" / "walk.py"
    planted.write_text("import os", encoding="utf-8")
    assert denied(guard, event("pp-walker", "Bash", command=walk_cmd(run, "look", walk=planted)))
    copy = tmp_path / "other" / "scripts" / "walk.py"
    copy.parent.mkdir(parents=True)
    shutil.copyfile(WALK, copy)
    assert guard.decide(event("pp-walker", "Bash", command=walk_cmd(run, "look", walk=copy))) is None


def test_panelist_and_synthesizer_may_not_use_bash(guard, run):
    for agent in ("pp-panelist", "persona-panel:pp-synthesizer"):
        assert denied(guard, event(agent, "Bash", command=walk_cmd(run, "look")))
        assert denied(guard, event(agent, "PowerShell", command="& " + walk_cmd(run, "look")))


def test_deny_reason_is_clear(guard, run):
    out = guard.decide(event("pp-panelist", "Bash", command="ls"))
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "persona-panel" in reason and "pp-panelist" in reason
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


# --- the process entry points -----------------------------------------------------------------------

def run_guard(args, payload, home, cwd):
    env = {**os.environ, "PERSONA_PANEL_HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(args, input=payload, capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(cwd))


def test_script_prints_deny_json_and_exits_0(home, run, tmp_path):
    r = run_guard([PY, str(HOOKS / "pp_guard.py")], json.dumps(event("pp-panelist", "Bash", command="ls")), home, tmp_path)
    assert r.returncode == 0
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    r = run_guard([PY, str(HOOKS / "pp_guard.py")], json.dumps(event("general-purpose", "Bash", command="ls")), home, tmp_path)
    assert r.returncode == 0 and r.stdout == ""
    for junk in ("", "not json", "[]"):
        r = run_guard([PY, str(HOOKS / "pp_guard.py")], junk, home, tmp_path)
        assert r.returncode == 0 and r.stdout == ""


def test_script_denies_pp_agent_when_it_crashes(home, run, tmp_path):
    bad = event("pp-walker", "Bash", command=None)
    r = run_guard([PY, str(HOOKS / "pp_guard.py")], json.dumps(bad), home, tmp_path)
    assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.skipif(not shutil.which("sh"), reason="needs a POSIX sh (Git Bash on Windows)")
def test_sh_launcher(home, run, tmp_path):
    sh = shutil.which("sh")
    r = run_guard([sh, str(HOOKS / "pp_guard.sh")], json.dumps(event("pp-walker", "Bash", command="ls")), home, tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    r = run_guard([sh, str(HOOKS / "pp_guard.sh")], json.dumps(event(None, "Bash", command="ls")), home, tmp_path)
    assert r.returncode == 0 and r.stdout == ""


def test_hooks_json_registers_the_guard():
    cfg = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    groups = cfg["hooks"]["PreToolUse"]
    assert len(groups) == 1 and "matcher" not in groups[0], "the guard must see every tool"
    hook = groups[0]["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/pp_guard.sh"'
    assert set(cfg["hooks"]) == {"PreToolUse"}


def test_guard_never_writes_bytecode(home, run, tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    env["PERSONA_PANEL_HOME"] = str(home)
    subprocess.run([PY, str(HOOKS / "pp_guard.py")], input=json.dumps(event("pp-panelist", "Bash", command="ls")),
                   capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert not list(HOOKS.rglob("__pycache__"))
