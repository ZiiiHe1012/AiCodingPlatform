"""Run learner code in an isolated container; the host only transports snapshots and results."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid

from flask import current_app, has_app_context

from .capacity import slot


class ServiceFault(Exception):
    """An infrastructure fault must never count as a failed student test."""


class TransientServiceFault(ServiceFault):
    """A temporary infrastructure error for which a delayed grading retry makes sense."""


class RunnerUnavailable(ServiceFault):
    """The isolated runner could not start the requested test."""


class TransientRunnerUnavailable(RunnerUnavailable, TransientServiceFault):
    """The container service is unavailable before student code starts."""


class Interrupted(Exception):
    pass


def _docker():
    cli = shutil.which("docker")
    if not cli:
        raise ServiceFault("运行器缺少 Docker，请启动 Docker 并构建 codelab-runner:2 镜像。")
    return cli


def _workspace_name(user_id, exam_id):
    if not user_id or not exam_id:
        raise ValueError("正式考试沙箱需要用户和考试编号。")
    database = current_app.config["DATABASE"] if has_app_context() else os.environ.get("CODELAB_DATABASE", "")
    namespace = str(Path(database).resolve())
    key = json.dumps([namespace, str(user_id), str(exam_id)], ensure_ascii=True).encode()
    return "codelab-exam-" + hashlib.sha256(key).hexdigest()[:36]


def _limits(memory, *, browser=False):
    return ["--init", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=" + ("256" if browser else "128"), "--cpus=1", "--memory=" + memory, "--memory-swap=" + memory,
            "--ulimit", "nofile=1024:1024" if browser else "nofile=256:256", "--user=65534:65534", "--log-driver=none",
            "--tmpfs", "/tmp:rw,nodev,nosuid,size=192m", "--shm-size=64m"]


def _owner(docker, name):
    cmd = [docker, "inspect", "--type", "container", "--format",
           '{{.State.Running}} {{index .Config.Labels "io.codelab.workspace"}} {{.Id}}', name]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    if result.returncode:
        if "no such container" in result.stderr.lower() or "no such object" in result.stderr.lower():
            return None
        raise TransientRunnerUnavailable("平台无法连接 Docker 服务，请老师或管理员检查它是否已启动。")
    parts = result.stdout.strip().split()
    if len(parts) != 3 or parts[1] != name:
        raise ServiceFault("考试沙箱名称已占用，无法确认容器归属。")
    return parts[0] == "true", parts[2]


def _acquire(docker, name, image):
    try:
        owned = _owner(docker, name)
        if owned and owned[0]:
            return owned[1]
        # docker run reserves the name atomically. A simultaneous launch may be
        # between create and start, so briefly wait for the same verified owner.
        result = subprocess.run([docker, "run", "-d", "--rm", "--pull=never", "--name", name,
                                 "--label", "io.codelab.workspace=" + name, *_limits("512m", browser=True),
                                 "--entrypoint", "/bin/sleep", image, "8h"],
                                capture_output=True, text=True, timeout=18)
        if result.returncode == 0:
            return result.stdout.strip()
        # Docker reserves a name before inspect can see the newly created container.
        # A worker starting the first command can race the background provisioner here.
        name_reserved = "already in use" in result.stderr.lower()
        for _ in range(30):
            owned = _owner(docker, name)
            if owned and owned[0]:
                return owned[1]
            if owned is None and not name_reserved:
                break
            time.sleep(.15)
        raise RunnerUnavailable(f"个人考试沙箱未能启动。请管理员在运行 CodeLab 的电脑上检查 Docker 和运行镜像 {image}。")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TransientRunnerUnavailable("Docker 未能及时创建考试沙箱。") from exc


def ensure_workspace(user_id, exam_id):
    """Start or reattach to a trusted user's exam container. Safe to call concurrently."""
    return _acquire(_docker(), _workspace_name(user_id, exam_id),
                    os.environ.get("CODELAB_RUNNER_IMAGE", "codelab-runner:2"))


def release_workspace(user_id, exam_id):
    """Idempotent end-of-exam cleanup. A missing daemon cannot prevent hand-in."""
    cli = shutil.which("docker")
    if not cli or not user_id or not exam_id:
        return False
    name = _workspace_name(user_id, exam_id)
    try:
        owned = _owner(cli, name)
        if owned:
            return subprocess.run([cli, "rm", "-f", owned[1]], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=8).returncode == 0
        return True
    except (OSError, subprocess.TimeoutExpired, ServiceFault):
        pass
    return False


def sandbox(project, instruction, problem, checkpoint=lambda: None, *, workspace=None):
    with slot("code", checkpoint):
        return _execute(project, instruction, problem, checkpoint, workspace=workspace)


def _execute(project, instruction, problem, checkpoint, *, workspace=None):
    docker = _docker()
    stack = problem["stack"].lower()
    runtime = "python" if "python" in stack else "node" if any(s in stack for s in ("typescript", "node", "vue", "javascript", "html")) else None
    if runtime is None:
        raise ServiceFault("该工程的技术栈尚未配置运行器。")
    limits = problem.get("evaluation") or {}
    preview = instruction["action"] == "preview"
    seconds = max(40 if preview else 1, min(int(limits.get("timeout", 30)), 120))
    memory = str(max(512 if preview else 64, min(int(limits.get("memory", 256)), 1024))) + "m"
    image = os.environ.get("CODELAB_RUNNER_IMAGE", "codelab-runner:2")
    serialized = json.dumps({"project": project, "runtime": runtime, "instruction": instruction},
                            ensure_ascii=True, allow_nan=False).encode()
    checkpoint()
    # Imported projects may specify a different memory limit from the shared exam workspace;
    # honor it with an equivalently isolated task container in that case.
    persistent = (workspace and workspace.get("exam_id") and memory == "512m"
                  and instruction["action"] in ("command", "preview"))
    if persistent:
        container = _acquire(docker, _workspace_name(workspace["user_id"], workspace["exam_id"]), image)
        argv = [docker, "exec", "-i", container, "/usr/bin/timeout"]
    else:
        container = "codelab-job-" + uuid.uuid4().hex
        argv = [docker, "run", "--rm", "-i", "--pull=never", "--name", container, *_limits(memory, browser=preview),
                "--entrypoint", "/usr/bin/timeout", image]
    argv += ["-k", "2", str(seconds), "python", "-I", "/opt/codelab/entry.py"]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        raise RunnerUnavailable("平台未能启动 Docker，请管理员检查运行环境。") from exc
    output = bytearray()
    truncated = threading.Event()
    cap = 2 * 1024 * 1024 if preview else 32768
    def read_output():
        with proc.stdout:
            while chunk := proc.stdout.read(8192):
                available = max(0, cap - len(output))
                output.extend(chunk[:available])
                if len(chunk) > available:
                    truncated.set()
    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    def write_input():
        try:
            with proc.stdin:
                proc.stdin.write(serialized)
        except (BrokenPipeError, OSError):
            pass
    writer = threading.Thread(target=write_input, daemon=True)
    writer.start()
    end = time.monotonic() + seconds + 15
    try:
        while proc.poll() is None:
            checkpoint()
            if time.monotonic() > end:
                raise TransientServiceFault("运行器未在预期时间响应。")
            time.sleep(.1)
    finally:
        # Killing the CLI alone does not stop the contained process.
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
            try:
                subprocess.run([docker, "rm", "-f", container], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                pass
        reader.join(timeout=3)
        writer.join(timeout=1)
    startup, _, remaining = output.partition(b"\n")
    if startup.strip() != b"CODELAB-RUNNER-READY/2":
        raise RunnerUnavailable(f"代码运行环境未就绪。请管理员在运行 CodeLab 的电脑上检查 Docker 服务和运行镜像 {image}。")
    text = remaining.decode("utf-8", "replace").strip()
    if truncated.is_set():
        text += "\n[输出已截断]"
    return {"code": proc.returncode, "output": text, "timed_out": proc.returncode == 124}


def build_preview(project, problem, workspace, checkpoint=lambda: None, *, actions=()):
    request = {"action": "preview", "input": {"actions": list(actions), "problem_id": problem["id"]}}
    result = sandbox(project, request, problem, checkpoint, workspace=workspace)
    if result["code"] != 0:
        reason = "网页预览超时。" if result["timed_out"] else result["output"][-1800:]
        raise ValueError(reason or "工程页面未能构建。")
    try:
        page = json.loads(result["output"].splitlines()[-1])
        if not isinstance(page, dict) or not isinstance(page.get("image"), str):
            raise ValueError()
        return page
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError("预览输出无效或超过大小限制。") from exc
