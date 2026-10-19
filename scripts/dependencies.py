#!/usr/bin/env python3
"""Generate Podman Containerfiles, Compose sidecars and Codex MCP from TOML.

Python >=3.11 stdlib only; install commands execute only inside build containers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "dependencies/dependencies.toml"
OUT = ROOT / ".generated"
IDENT = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+.:~_-]*$")


def err(msg):
    raise ValueError(msg)


def strings(value, where):
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        err(where + ": expected nonempty string array")
    return value


def file_path(value, folder):
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        err("Unsafe local file: " + repr(value))
    root = (ROOT / "dependencies" / folder).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
        err("Local dependency missing or unsafe: " + repr(value))
    return path


def check_archive(path):
    def check(name, ordinary):
        p = PurePosixPath(name)
        if not ordinary or p.is_absolute() or ".." in p.parts or not name:
            err("Unsafe archive entry: " + repr(name))
    if path.name.endswith((".tar", ".tar.gz", ".tar.xz", ".tgz")):
        with tarfile.open(path) as archive:
            for member in archive:
                check(member.name, member.isdir() or member.isfile())
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                mode = (member.external_attr >> 16) & 0o170000
                check(member.filename, mode in (0, 0o100000, 0o040000))
    else:
        err("Unsupported archive: " + path.name)


def check_step(step, where):
    if not isinstance(step, dict):
        err(where + " must be a table")
    typ = step.get("type")
    allowed = {"type", "id", "verify"}
    if typ not in ("apt", "deb", "script", "command", "archive"):
        err(where + ": invalid install type")
    if "id" in step and (not isinstance(step["id"], str) or not IDENT.fullmatch(step["id"])):
        err(where + ": invalid id")
    strings(step.get("verify", []), where + ".verify")
    allowed.add("files")
    for resource in strings(step.get("files", []), where + ".files"):
        file_path(resource, "files")
    if typ == "apt":
        allowed.add("packages")
        for pkg in strings(step.get("packages"), where + ".packages"):
            if not PACKAGE.fullmatch(pkg):
                err(where + ": invalid apt package " + pkg)
    if typ in ("deb", "script", "archive"):
        allowed.add("file")
        category = "scripts" if typ == "script" else "packages"
        source = file_path(step.get("file"), category)
        if typ == "deb" and source.suffix != ".deb":
            err(where + ": expected deb")
        if typ == "script":
            allowed.add("args")
            strings(step.get("args", []), where + ".args")
        if typ == "archive":
            allowed.add("destination")
            dest = step.get("destination")
            if not isinstance(dest, str) or not dest.startswith("/") or dest == "/" or ".." in PurePosixPath(dest).parts:
                err(where + ": unsafe destination")
            check_archive(source)
    if typ == "command":
        allowed.add("run")
        if not isinstance(step.get("run"), str) or not step["run"].strip():
            err(where + ": missing command")
    if set(step) - allowed:
        err(where + ": unsupported keys " + repr(set(step)-allowed))


def parse(path=CONFIG):
    data = tomllib.loads(path.read_text())
    if set(data) - {"base", "apt", "install", "agent_tools", "project"}:
        err("Unknown top-level sections")
    if data.get("base", {}).get("image", "debian:13-slim") not in ("debian:13-slim", "docker.io/library/debian:13-slim"):
        err("This release supports Debian 13 slim only")
    apt = data.get("apt", {})
    if set(apt) - {"packages"}:
        err("Unknown apt settings")
    check_step({"type": "apt", "packages": apt.get("packages", [])}, "apt")
    installs = data.get("install", [])
    if not isinstance(installs, list):
        err("install must be an array")
    for i, step in enumerate(installs):
        check_step(step, "install[" + str(i) + "]")
    seen = set()
    tools = data.get("agent_tools", [])
    if not isinstance(tools, list):
        err("agent_tools must be an array")
    for tool in tools:
        if not isinstance(tool, dict):
            err("agent_tools entries must be tables")
        tid = tool.get("id")
        if not isinstance(tid, str) or not IDENT.fullmatch(tid) or tid in seen:
            err("Invalid/duplicate agent tool id: " + str(tid))
        seen.add(tid)
        if set(tool) - {"id", "enabled", "placement", "kind", "install", "runtime", "integration", "state", "lsp"}:
            err("Unknown agent tool fields")
        if not isinstance(tool.get("enabled", True), bool):
            err("Tool enabled must be bool")
        where, kind = tool.get("placement"), tool.get("kind")
        if where not in ("embedded", "sidecar", "external") or kind not in ("mcp", "cli"):
            err(tid + ": invalid placement/kind")
        toolsteps = tool.get("install", [])
        if not isinstance(toolsteps, list):
            err("Tool install must be an array")
        for i, step in enumerate(toolsteps):
            check_step(step, tid + ".install[" + str(i) + "]")
        run, it = tool.get("runtime", {}), tool.get("integration", {})
        lsp = tool.get("lsp")
        if lsp is not None:
            if not isinstance(lsp, dict) or set(lsp) != {"adapter", "servers"}:
                err(tid + ": lsp requires adapter and servers")
            if lsp["adapter"] != "serena":
                err(tid + ": unsupported LSP consumer adapter (currently: serena)")
            servers = lsp["servers"]
            if not isinstance(servers, dict) or not servers:
                err(tid + ": lsp.servers must be nonempty")
            for language, executable in servers.items():
                if not isinstance(language, str) or not IDENT.fullmatch(language):
                    err(tid + ": invalid LSP language identifier")
                if not isinstance(executable, str) or not executable.startswith("/") or ".." in PurePosixPath(executable).parts or any(ch.isspace() for ch in executable):
                    err(tid + ": LSP executable must be a safe absolute path")
            if kind != "mcp" or where != "embedded" or tool.get("integration", {}).get("transport") != "stdio":
                err(tid + ": Serena LSP binding requires embedded MCP stdio")
            if tool.get("state", {}).get("target") != "/root/.serena":
                err(tid + ": Serena LSP binding requires persistent /root/.serena state")
        state = tool.get("state", {})
        if not isinstance(state, dict) or set(state) - {"base", "target"}:
            err(tid + ": invalid tool state fields")
        if state:
            base = state.get("base", "./volumes/tools/" + tid)
            mount = state.get("target")
            if not isinstance(base, str) or not (base.startswith("./volumes/") or base.startswith("volumes/")) or ".." in Path(base).parts:
                err(tid + ": state base must be under this repository's volumes/")
            if not isinstance(mount, str) or not mount.startswith("/") or mount == "/" or ".." in PurePosixPath(mount).parts:
                err(tid + ": state target must be an absolute container directory")
            if where == "external":
                err(tid + ": external tool cannot mount local state")
        if not isinstance(run, dict) or not isinstance(it, dict):
            err(tid + ": invalid runtime/integration")
        if where == "external" and (toolsteps or run):
            err("External tools cannot install local binaries")
        if where == "sidecar":
            strings(run.get("command"), tid + ".runtime.command")
            port = run.get("port")
            if type(port) is not int or port < 1 or port > 65535:
                err(tid + ": invalid sidecar port")
            if set(run) - {"command", "port"}:
                err("Unknown sidecar runtime field")
        elif run:
            err("Runtime only for sidecars")
        if kind == "cli":
            if where != "embedded" or it:
                err("CLI tools must be embedded without integration")
        else:
            transport = it.get("transport")
            if transport == "stdio":
                cmd = it.get("command")
                if where != "embedded" or not isinstance(cmd, str) or not cmd.startswith("/"):
                    err("stdio MCP requires embedded executable absolute path")
                strings(it.get("args", []), tid + ".args")
                if set(it) - {"transport", "command", "args"}:
                    err("Invalid stdio integration fields")
            elif transport == "http":
                if where == "embedded":
                    err("HTTP tools must be sidecar or external")
                if where == "external":
                    url = it.get("url")
                    if not isinstance(url, str) or not url.startswith("https://"):
                        err("External MCP must have HTTPS URL")
                    if set(it) - {"transport", "url"}:
                        err("Invalid external integration fields")
                else:
                    endpoint = it.get("path", "/mcp")
                    if not isinstance(endpoint, str) or not endpoint.startswith("/") or ".." in endpoint:
                        err("Invalid sidecar HTTP path")
                    if set(it) - {"transport", "path"}:
                        err("Invalid sidecar integration fields")
            else:
                err("MCP transport must be stdio or http")
    project = data.get("project", {})
    if not isinstance(project, dict) or set(project) - {"test", "race", "integration", "lint"}:
        err("Invalid project tasks")
    if not all(isinstance(c, str) for c in project.values()):
        err("Project tasks must be commands")
    return data


def run_line(command):
    return "RUN " + json.dumps(["/bin/bash", "-euo", "pipefail", "-c", command])


def steps(lines, items):
    for step in items:
        typ = step["type"]
        lines.append("# " + step.get("id", typ))
        for resource in step.get("files", []):
            source = "dependencies/files/" + resource
            target_resource = "/opt/isolated-install/files/" + resource
            lines.append("COPY " + json.dumps([source, target_resource]))
        if typ in ("deb", "script", "archive"):
            folder = "scripts" if typ == "script" else "packages"
            path = step["file"]
            target = "/opt/isolated-install/" + folder + "/" + path
            lines.append("COPY " + json.dumps(["dependencies/" + folder + "/" + path, target]))
        if typ == "apt":
            pkgs = " ".join(shlex.quote(x) for x in step["packages"])
            command = ("apt-get update && apt-get install -y --no-install-recommends " + pkgs + " && rm -rf /var/lib/apt/lists/*") if pkgs else "true"
        elif typ == "deb":
            command = "apt-get update && apt-get install -y --no-install-recommends " + shlex.quote(target) + " && rm -rf /var/lib/apt/lists/*"
        elif typ == "script":
            command = "bash " + shlex.quote(target) + " " + " ".join(shlex.quote(x) for x in step.get("args", []))
        elif typ == "archive":
            d = shlex.quote(step["destination"])
            command = ("mkdir -p " + d + " && unzip -q " + shlex.quote(target) + " -d " + d) if target.endswith(".zip") else ("mkdir -p " + d + " && tar -xf " + shlex.quote(target) + " -C " + d)
        else:
            command = step["run"]
        lines.append(run_line(command))
        for test in step.get("verify", []):
            lines.append(run_line(test))



def state_dir(tool, project_name):
    state = tool.get("state", {})
    if not state:
        return None
    key = os.environ.get("CODEX_PROJECT_KEY", "")
    if not re.fullmatch(r"[0-9a-f]{24}", key):
        project_dir = (ROOT / os.environ.get("PROJECT_DIR", "./workspace")).resolve()
        key = hashlib.sha256((project_name + "\0" + str(project_dir)).encode()).hexdigest()[:24]
    return (ROOT / state.get("base", "./volumes/tools/" + tool["id"]) / key).resolve()


def prepare_tool_state(data):
    project_name = os.environ.get("COMPOSE_PROJECT_NAME", "isolated-agent-demo")
    for tool in enabled(data):
        path = state_dir(tool, project_name)
        if path is None:
            continue
        if not path.is_relative_to((ROOT / "volumes").resolve()) or path.is_symlink():
            err("Unsafe tool persistent state path: " + str(path))
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not path.is_dir():
            err("Tool state directory not accessible: " + str(path))
        print("Tool state ready:", tool["id"], path)


def enabled(data):
    return [t for t in data.get("agent_tools", []) if t.get("enabled", True)]


def generate(data, folder=OUT):
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["# Generated file: no manual changes.",
             "ARG CODEX_IMAGE=localhost/isolated-agent-codex:dev",
             "FROM " + "$" + "{CODEX_IMAGE}", "WORKDIR /workspace"]
    steps(lines, [{"type": "apt", "packages": data.get("apt", {}).get("packages", [])}])
    steps(lines, data.get("install", []))
    for tool in enabled(data):
        if tool["placement"] == "embedded":
            lines.append("# Embedded tool: " + tool["id"])
            steps(lines, tool.get("install", []))
    (folder / "Containerfile.dependencies").write_text("\n".join(lines) + "\n")
    project_name = os.environ.get("COMPOSE_PROJECT_NAME", "isolated-agent-demo")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", project_name):
        err("Unsafe Compose project name for MCP DNS")
    sidecars = []
    compose = ["# Generated sidecar overlay", "services:"]
    agent_states = [(t, state_dir(t, project_name)) for t in enabled(data) if t["placement"] == "embedded" and t.get("state")]
    if agent_states:
        compose += ["  agent:", "    volumes:"]
        for t, path in agent_states:
            compose.append("      - " + json.dumps(str(path) + ":" + t["state"]["target"] + ":rw"))
    mcp = ["# Generated MCP configuration"]
    for tool in enabled(data):
        tid, where, kind = tool["id"], tool["placement"], tool["kind"]
        if where == "sidecar":
            sidecars.append(tid)
            side = ["ARG BASE_IMAGE=localhost/isolated-agent-base:dev", "FROM " + "$" + "{BASE_IMAGE}", "WORKDIR /workspace"]
            steps(side, tool.get("install", []))
            (folder / ("Containerfile.tool-" + tid)).write_text("\n".join(side) + "\n")
            alias = project_name + "-tool-" + tid
            compose += ["  tool-" + tid + ":",
                        "    image: localhost/isolated-agent-tool-" + project_name + "-" + tid + ":dev",
                        "    read_only: true", "    cap_drop:", "      - ALL",
                        "    security_opt:", "      - no-new-privileges:true",
                        "    volumes:", "      - " + "$" + "{PROJECT_DIR:-./workspace}:/workspace:ro",
                        *([] if not tool.get("state") else ["      - " + json.dumps(str(state_dir(tool, project_name)) + ":" + tool["state"]["target"] + ":rw")]),
                        "    tmpfs:", "      - /tmp:rw,nosuid,nodev,size=128m",
                        "    networks:", "      isolated-dev:", "        aliases:", "          - " + alias,
                        "    command: " + json.dumps(tool["runtime"]["command"])]
        if kind != "mcp":
            continue
        i = tool["integration"]
        mcp += ["", "[mcp_servers." + tid + "]"]
        if i["transport"] == "stdio":
            mcp += ["command = " + json.dumps(i["command"]), "args = " + json.dumps(i.get("args", []))]
        else:
            url = i["url"] if where == "external" else ("http://" + project_name + "-tool-" + tid + ":" + str(tool["runtime"]["port"]) + i.get("path", "/mcp"))
            mcp += ["url = " + json.dumps(url)]
    # An empty services mapping needs {}, but an agent-only overlay already
    # contains a valid mapping. Appending {} to its final volume line breaks
    # YAML parsing (notably for embedded Serena with persistent state).
    if len(compose) == 2:
        compose[1] = "services: {}"
    (folder / "compose.tools.yaml").write_text("\n".join(compose) + "\n")
    (folder / "codex-mcp.toml").write_text("\n".join(mcp) + "\n")
    # Consumer adapters are explicit. An empty file is a no-op at runtime.
    lsp_bindings = []
    for tool in enabled(data):
        binding = tool.get("lsp")
        if not binding:
            continue
        tool_bin = PurePosixPath(tool["integration"]["command"])
        lsp_bindings.append({
            "tool": tool["id"],
            "adapter": binding["adapter"],
            "state": tool["state"]["target"],
            "python": str(tool_bin.parent / "python"),
            "command": tool["integration"]["command"],
            "servers": binding["servers"],
        })
    (folder / "tool-lsp.json").write_text(json.dumps(lsp_bindings, indent=2, sort_keys=True) + "\n")
    (folder / "project-commands.json").write_text(json.dumps(data.get("project", {}), indent=2) + "\n")
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode())
    for step in data.get("install", []) + [s for t in enabled(data) for s in t.get("install", [])]:
        if step["type"] in ("script", "deb", "archive"):
            digest.update(file_path(step["file"], "scripts" if step["type"] == "script" else "packages").read_bytes())
        for resource in step.get("files", []):
            digest.update(file_path(resource, "files").read_bytes())
    summary = {"fingerprint": digest.hexdigest()[:16], "sidecars": sidecars}
    (folder / "manifest.json").write_text(json.dumps(summary) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate", "plan", "generate", "build", "project-command", "sidecar-services", "tool-state"))
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--engine", default="podman")
    parser.add_argument("--base-image", default="localhost/isolated-agent-base:dev")
    parser.add_argument("--codex-image", default="localhost/isolated-agent-codex:dev")
    parser.add_argument("--deps-image", default="localhost/isolated-agent-dependencies:dev")
    parser.add_argument("--name", default="")
    args = parser.parse_args()
    try:
        data = parse(args.config)
        if args.action == "validate":
            print("Dependencies config valid")
            return 0
        if args.action == "tool-state":
            prepare_tool_state(data)
            return 0
        if args.action == "sidecar-services":
            print(" ".join("tool-" + x["id"] for x in enabled(data) if x["placement"] == "sidecar"))
            return 0
        if args.action == "project-command":
            value = data.get("project", {}).get(args.name, "")
            if not value:
                err("No project command " + args.name + " configured")
            print(value)
            return 0
        summary = generate(data)
        print("Dependencies:", summary)
        if args.action != "build":
            return 0
        subprocess.run([args.engine, "build", "-f", str(OUT / "Containerfile.dependencies"),
                        "--build-arg", "CODEX_IMAGE=" + args.codex_image, "-t",
                        args.deps_image, "."], cwd=ROOT, check=True)
        for name in summary["sidecars"]:
            subprocess.run([args.engine, "build", "-f", str(OUT / ("Containerfile.tool-" + name)),
                            "--build-arg", "BASE_IMAGE=" + args.base_image,
                            "-t", "localhost/isolated-agent-tool-" + os.environ.get("COMPOSE_PROJECT_NAME", "isolated-agent-demo") + "-" + name + ":dev", "."],
                           cwd=ROOT, check=True)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
