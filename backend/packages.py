"""Validate uploaded task archives entirely as data; keep teachers' fixtures private."""
import io
import json
from pathlib import PurePosixPath
import stat
import zipfile
import zlib

from flask import request, send_file, url_for
from werkzeug.exceptions import HTTPException

from .catalog import (bp, owned_bank, problems_with, public_metadata, store_project,
                      text_field, reserve_write, get_project_row, managed_bank_by_project, version_parts)
from .core import audit, body, db, fail, files, ident, obj, ok, uid
from .grading import parse_private_tests

MAX_ZIP = 20 * 1024 * 1024
MAX_UNPACKED = 100 * 1024 * 1024
SUFFIXES = {".json", ".md", ".py", ".txt", ".ts", ".js", ".vue", ".html", ".css",
            ".toml", ".yaml", ".yml", ".log", ".csv"}
INSTALLERS = {"setup.py", "install.py", "install.js", "configure", "makefile"}


class InvalidPackage(ValueError):
    def __init__(self, path, message, field=""):
        super().__init__(message)
        self.item = {"file": path, "field": field, "message": message, "severity": "error"}


def read_archive(buffer):
    content = {}
    try:
        with zipfile.ZipFile(io.BytesIO(buffer)) as archive:
            members = archive.infolist()
            if len(members) > 1000 or sum(m.file_size for m in members) > MAX_UNPACKED:
                raise InvalidPackage("", "最多1000个条目，解压总量上限100MB")
            paths = set()
            for member in members:
                path = member.filename.rstrip("/")
                parts = path.split("/")
                mode = member.external_attr >> 16
                if (not path or any(p in ("", ".", "..") for p in parts) or "\\" in path
                        or ":" in path or any(ord(c) < 32 for c in member.orig_filename)
                        or len(path) > 255 or path.casefold() in paths):
                    raise InvalidPackage(path, "无效或重复的压缩包路径")
                if stat.S_IFMT(mode) not in (0, stat.S_IFDIR, stat.S_IFREG) or member.flag_bits & 1:
                    raise InvalidPackage(path, "仅支持未加密的普通文本文件和目录")
                if any(p.casefold() in (".git", "node_modules", "__pycache__") for p in parts):
                    raise InvalidPackage(path, "请移除版本控制、依赖或缓存目录")
                paths.add(path.casefold())
                if member.is_dir():
                    continue
                filename = PurePosixPath(path)
                if filename.suffix.lower() not in SUFFIXES or filename.name.lower() in INSTALLERS:
                    raise InvalidPackage(path, "文件不在题包白名单")
                try:
                    content[path] = archive.read(member).decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise InvalidPackage(path, "文本须使用UTF-8编码") from exc
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, zlib.error) as exc:
        raise InvalidPackage("", "压缩格式、内容或校验码无效") from exc
    return content


def select_tree(content, prefix):
    return {k[len(prefix):]: v for k, v in content.items() if k.startswith(prefix)}


def srs_project(manifest, content):
    # schema 1 is the course SRS layout; schema 2 is the engineering preview export.
    required = ("title", "task_type", "language", "limits", "tags", "source", "rubric")
    for key in required:
        if key not in manifest:
            raise InvalidPackage("manifest.json", "缺少清单字段", key)
    if str(manifest["language"]).lower() not in ("python", "python3", "python3.12", "python 3.12"):
        raise InvalidPackage("manifest.json", "该格式的测评语言须为Python", "language")
    starter = select_tree(content, "starter/")
    public = select_tree(content, "tests/public/")
    test_files = {"tests/" + name: text for name, text in public.items()}
    if not starter or not public or set(starter).intersection(test_files):
        raise InvalidPackage("starter/", "应提供模板与公开测试，且公开文件路径不能冲突")
    statement = content.get("statement.md", "").strip()
    if not statement:
        raise InvalidPackage("statement.md", "缺少工程任务说明")
    limits = manifest["limits"]
    if not isinstance(limits, dict):
        raise InvalidPackage("manifest.json", "应为时间和内存设置对象", "limits")
    rubric = manifest["rubric"]
    if isinstance(rubric, dict):
        rubric = rubric.get("weights")
    if not isinstance(rubric, list):
        raise InvalidPackage("manifest.json", "量规须包含D1到D6的六项权重", "rubric")
    task_map = {"implementation": "需求实现", "algorithm": "算法实现", "bugfix": "缺陷修复",
                "completion": "功能补全", "testing": "测试编写", "refactor": "工程重构"}
    task_type = manifest["task_type"]
    if not isinstance(task_type, str):
        raise InvalidPackage("manifest.json", "任务类型应为文本", "task_type")
    return {"title": manifest["title"], "description": statement, "type": task_map.get(task_type, task_type),
            "stack": "Python 3.12 / pytest", "difficulty": manifest.get("difficulty", "中等"),
            "tags": manifest["tags"], "repository": manifest.get("repository", "python-project"),
            "entryFile": manifest.get("entry_file", next((p for p in starter if p.endswith(".py") and not p.endswith("__init__.py")), "")),
            "duration": manifest.get("duration", 60), "requirements": manifest.get("requirements", [statement]),
            "acceptance": manifest.get("acceptance", [{"id": "AC-1", "scenario": "运行项目验收测试", "expected": "满足题面要求并通过测试"}]),
            "constraints": manifest.get("constraints", []), "deliverables": manifest.get("deliverables", ["项目代码与测试", "验证说明"]),
            "commands": {"setup": "", "test": "python -m pytest -q", "start": ""},
            "evaluation": {"timeout": limits.get("timeout", limits.get("time_seconds", 10)),
                           "memory": limits.get("memory", limits.get("memory_mb", 512))},
            "source": manifest["source"], "weights": rubric, "files": {**starter, **test_files}}


def inspect_package(buffer):
    content = read_archive(buffer)
    try:
        manifest = json.loads(content.get("manifest.json", ""))
    except (ValueError, RecursionError) as exc:
        raise InvalidPackage("manifest.json", "缺少清单或JSON格式错误") from exc
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int:
        raise InvalidPackage("manifest.json", "schema_version须为1或2", "schema_version")
    if manifest["schema_version"] == 2:
        raw = manifest.get("project")
        if not isinstance(raw, dict):
            raise InvalidPackage("manifest.json", "project应为工程描述对象", "project")
        raw = {**raw, "files": select_tree(content, "project/")}
    elif manifest["schema_version"] == 1:
        raw = srs_project(manifest, content)
    else:
        raise InvalidPackage("manifest.json", "不支持此版本", "schema_version")
    private = select_tree(content, "tests/hidden/")
    reference = select_tree(content, "reference/")
    if manifest["schema_version"] == 1 and (not private or not reference):
        raise InvalidPackage("tests/hidden/", "课程规格题包需提供隐藏验收与reference/参考实现")
    if private:
        try:
            parse_private_tests(private)
        except ValueError as exc:
            raise InvalidPackage("tests/hidden/cases.json", str(exc)) from exc
    try:
        data = public_metadata(raw)
    except HTTPException as exc:
        raise InvalidPackage("manifest.json", str(exc.description)) from exc
    issues = problems_with(data)
    if not private:
        issues.append({"file": "tests/hidden/cases.json", "field": "", "severity": "warning",
                       "message": "题包未提供D1/D2隐藏验收，正式成绩需要人工复核。"})
    if not any(i["severity"] == "error" for i in issues):
        return {"project": data, "private": private, "reference": reference}, issues
    return None, issues


def author_materials(raw, previous=None):
    if "author_materials" not in raw:
        return tuple(json.loads(previous[key]) if previous else {}
                     for key in ("private_tests", "reference_files"))
    materials = raw["author_materials"]
    if not isinstance(materials, dict) or set(materials) != {"private_tests", "reference_files"}:
        fail(422, "请提供隐藏验收与参考文件两个文件映射")
    private, reference = (materials[k] for k in ("private_tests", "reference_files"))
    for mapping in (private, reference):
        if mapping != {}:
            files(mapping)
    if private:
        try:
            parse_private_tests(private)
        except ValueError as exc:
            fail(422, str(exc))
    for path in reference:
        name = PurePosixPath(path)
        if (name.suffix.lower() not in SUFFIXES or name.name.casefold() in INSTALLERS
                or any(p.casefold() in {".git", "node_modules", "__pycache__"} for p in name.parts)):
            fail(422, "参考文件路径或扩展名不在题包白名单")
    return private, reference


@bp.get("/problem-versions/<ref>/author-materials")
def get_author_materials(ref):
    project, version = version_parts(ref, None)
    managed_bank_by_project(project)
    row = get_project_row(project, version, manage=True)
    return ok({key: json.loads(row[key]) for key in ("private_tests", "reference_files")})


@bp.get("/problem-versions/<ref>/package")
def export_package(ref):
    project, version = version_parts(ref, None)
    author = request.args.get("author") == "1"
    if author:
        managed_bank_by_project(project)
    row = get_project_row(project, version, manage=author)
    metadata = public_metadata(json.loads(row["metadata"]))
    public_files = metadata.pop("files")
    artifact = io.BytesIO()
    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", obj({"schema_version": 2, "project": metadata}))
        for path, content in public_files.items():
            archive.writestr("project/" + path, content)
        if author:
            for prefix, column in (("tests/hidden/", "private_tests"), ("reference/", "reference_files")):
                for path, content in json.loads(row[column]).items():
                    archive.writestr(prefix + path, content)
    artifact.seek(0)
    response = send_file(artifact, mimetype="application/zip", as_attachment=True,
                         download_name=f"{project}-{row['version']}.zip", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.post("/banks/<bank_id>/imports/upload-url")
def upload_url(bank_id):
    bank = owned_bank(bank_id)
    data = body()
    name = text_field(data.get("name"), "文件名", 255)
    size = data.get("size")
    if not name.lower().endswith(".zip") or type(size) is not int or size <= 0:
        fail(400, "请选择非空 ZIP 题包")
    if size > MAX_ZIP:
        fail(413, "ZIP 文件超过20 MB")
    key = ident("upload")
    db().execute("INSERT INTO project_imports(id,bank_id,owner_id,filename) VALUES(?,?,?,?)",
                 (key, bank["id"], uid(), name))
    db().commit()
    return ok({"upload_url": url_for(".upload", bank_id=bank["id"], key=key), "object_id": key}, 201)


def import_item(bank_id, key, attr):
    bank = owned_bank(bank_id)
    row = db().execute(f"SELECT * FROM project_imports WHERE {attr}=? AND bank_id=? AND owner_id=?",
                       (key, bank["id"], uid())).fetchone()
    if not row:
        fail(404, "未找到该题库的导入任务")
    return row


@bp.put("/banks/<bank_id>/imports/uploads/<key>")
def upload(bank_id, key):
    import_item(bank_id, key, "id")
    if request.content_length and request.content_length > MAX_ZIP:
        fail(413, "ZIP 文件超过20 MB")
    data = request.stream.read(MAX_ZIP + 1)
    if not data or len(data) > MAX_ZIP:
        fail(413 if data else 400, "题包应为1字节至20MB")
    if not db().execute("UPDATE project_imports SET contents=? WHERE id=? AND contents IS NULL AND validation_id IS NULL",
                        (data, key)).rowcount:
        fail(409, "请新建上传任务")
    db().commit()
    return ok({"object_id": key})


@bp.post("/banks/<bank_id>/imports/validate")
def validate(bank_id):
    key = text_field(body().get("object_id"), "object_id")
    row = import_item(bank_id, key, "id")
    if row["validation_id"]:
        return ok(json.loads(row["result"])["report"])
    if row["contents"] is None:
        fail(409, "请先上传题包")
    try:
        checked, items = inspect_package(row["contents"])
    except InvalidPackage as exc:
        checked, items = None, [exc.item]
    validation_id = ident("validation")
    report = {"validation_id": validation_id, "valid": checked is not None, "items": items,
              "titles": [checked["project"]["title"]] if checked else []}
    cached = obj({"report": report, "checked": checked})
    db().execute("""UPDATE project_imports SET validation_id=?, result=?, contents=NULL
                 WHERE id=? AND validation_id IS NULL""", (validation_id, cached, key))
    db().commit()
    row = import_item(bank_id, key, "id")
    return ok(json.loads(row["result"])["report"])


@bp.post("/banks/<bank_id>/imports")
def confirm(bank_id):
    validation_id = text_field(body().get("validation_id"), "validation_id")
    # Serialize concurrent confirms before checking whether a project already exists.
    reserve_write()
    row = import_item(bank_id, validation_id, "validation_id")
    if row["created_project"]:
        return ok({"problem_id": row["created_project"], "imported": 1})
    checked = json.loads(row["result"])["checked"]
    if checked is None:
        fail(409, "预检未通过")
    project = store_project(owned_bank(bank_id), checked["project"], checked["private"], checked["reference"])
    db().execute("UPDATE project_imports SET created_project=? WHERE id=?", (project, row["id"]))
    audit("导入题包", f"{row['filename']} → {project}")
    db().commit()
    return ok({"problem_id": project, "imported": 1}, 201)
