

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import resolve_tool_path

_DEFAULT_YAML = "docs/contract.openapi.yaml"
_DEFAULT_PY_OUT = "backend/contract/schemas.py"
_DEFAULT_TS_OUT = "web/src/types/contract.ts"

class ContractCodegenTool(BaseTool):


    @property
    def name(self) -> str:
        return "contract_codegen"

    @property
    def description(self) -> str:
        return (
            "从 workspace/docs/contract.openapi.yaml 生成后端 Pydantic 模型（schemas.py）"
            "与前端 TypeScript 类型（contract.ts），让双端共享同一事实源。"
            "应在 architect 完成契约后、specialist 开工前调用。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "contract_codegen",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "yaml_path": {
                            "type": "string",
                            "description": f"OpenAPI YAML 文件路径（相对 workspace/），默认 {_DEFAULT_YAML}",
                        },
                        "python_out": {
                            "type": "string",
                            "description": f"Pydantic 输出路径（相对 workspace/），默认 {_DEFAULT_PY_OUT}",
                        },
                        "typescript_out": {
                            "type": "string",
                            "description": f"TypeScript 输出路径（相对 workspace/），默认 {_DEFAULT_TS_OUT}",
                        },
                        "targets": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["python", "typescript"]},
                            "description": "生成哪些语言，默认 ['python','typescript']",
                        },
                        "prefer_external": {
                            "type": "boolean",
                            "description": "True 优先调用 datamodel-codegen / openapi-typescript；False 直接走内置极简生成器（默认 True）",
                        },
                    },
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        yaml_rel = kwargs.get("yaml_path") or _DEFAULT_YAML
        py_rel = kwargs.get("python_out") or _DEFAULT_PY_OUT
        ts_rel = kwargs.get("typescript_out") or _DEFAULT_TS_OUT
        targets = set(kwargs.get("targets") or ["python", "typescript"])
        prefer_external = bool(kwargs.get("prefer_external", True))


        yaml_path, err = resolve_tool_path(yaml_rel)
        if err:
            return ToolResult(success=False, error=f"解析 yaml 路径失败: {err}")
        if not yaml_path.exists():
            return ToolResult(
                success=False,
                error=(
                    f"OpenAPI 文件不存在: {yaml_path}\n"
                    "请先让 architect 产出 workspace/docs/contract.openapi.yaml。"
                ),
            )


        py_path, err_py = resolve_tool_path(py_rel) if "python" in targets else (None, None)
        if err_py:
            return ToolResult(success=False, error=f"解析 python_out 失败: {err_py}")
        ts_path, err_ts = resolve_tool_path(ts_rel) if "typescript" in targets else (None, None)
        if err_ts:
            return ToolResult(success=False, error=f"解析 typescript_out 失败: {err_ts}")


        try:
            import yaml
        except ImportError:
            return ToolResult(success=False, error="PyYAML 未安装（异常：项目应已依赖），请检查环境")

        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                spec = yaml.safe_load(f)
        except Exception as e:
            return ToolResult(success=False, error=f"解析 YAML 失败: {type(e).__name__}: {e}")

        if not isinstance(spec, dict) or "paths" not in spec or "components" not in spec:
            return ToolResult(
                success=False,
                error="OpenAPI 结构异常：缺少 paths/components。architect 产物请遵循 OpenAPI 3.1。",
            )

        report: dict[str, Any] = {
            "yaml_path": str(yaml_path),
            "python": {"attempted": "python" in targets, "generator": None, "output": None, "warnings": []},
            "typescript": {"attempted": "typescript" in targets, "generator": None, "output": None, "warnings": []},
        }


        if "python" in targets and py_path is not None:
            ok, gen, warns = await self._generate_python(yaml_path, py_path, spec, prefer_external)
            report["python"]["generator"] = gen
            report["python"]["output"] = str(py_path) if ok else None
            report["python"]["warnings"] = warns
            if not ok:
                report["python"]["error"] = warns[-1] if warns else "unknown"


        if "typescript" in targets and ts_path is not None:
            ok, gen, warns = await self._generate_typescript(yaml_path, ts_path, spec, prefer_external)
            report["typescript"]["generator"] = gen
            report["typescript"]["output"] = str(ts_path) if ok else None
            report["typescript"]["warnings"] = warns
            if not ok:
                report["typescript"]["error"] = warns[-1] if warns else "unknown"


        summary = self._summarize(report)
        overall_ok = (
            ("python" not in targets or report["python"].get("output"))
            and ("typescript" not in targets or report["typescript"].get("output"))
        )
        return ToolResult(success=overall_ok, output=summary, data=report)





    async def _generate_python(
        self, yaml_path: Path, out_path: Path, spec: dict, prefer_external: bool
    ) -> tuple[bool, str, list[str]]:
        warns: list[str] = []
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if prefer_external and shutil.which("datamodel-codegen"):
            try:
                code, so, se = await _run_cmd(
                    [
                        "datamodel-codegen",
                        "--input", str(yaml_path),
                        "--input-file-type", "openapi",
                        "--output", str(out_path),
                        "--output-model-type", "pydantic_v2.BaseModel",
                        "--use-schema-description",
                        "--use-field-description",
                        "--target-python-version", "3.11",
                    ],
                    timeout=60,
                )
                if code == 0 and out_path.exists():
                    return True, "datamodel-codegen", warns
                warns.append(f"datamodel-codegen 退出码 {code}: {se.strip()[:200]}")
            except Exception as e:
                warns.append(f"调用 datamodel-codegen 异常: {e}")


        try:
            code_text = _builtin_pydantic(spec)
            out_path.write_text(code_text, encoding="utf-8")
            warns.append("使用内置极简生成器（不支持 allOf/oneOf 等高级特性）。")
            return True, "builtin", warns
        except Exception as e:
            warns.append(f"内置生成器失败: {type(e).__name__}: {e}")
            return False, "builtin", warns





    async def _generate_typescript(
        self, yaml_path: Path, out_path: Path, spec: dict, prefer_external: bool
    ) -> tuple[bool, str, list[str]]:
        warns: list[str] = []
        out_path.parent.mkdir(parents=True, exist_ok=True)


        if prefer_external and shutil.which("npx"):
            try:
                code, so, se = await _run_cmd(
                    ["npx", "--yes", "openapi-typescript", str(yaml_path), "-o", str(out_path)],
                    timeout=120,
                )
                if code == 0 and out_path.exists():
                    return True, "openapi-typescript", warns
                warns.append(f"openapi-typescript 退出码 {code}: {se.strip()[:200]}")
            except Exception as e:
                warns.append(f"调用 openapi-typescript 异常: {e}")


        try:
            code_text = _builtin_typescript(spec)
            out_path.write_text(code_text, encoding="utf-8")
            warns.append("使用内置极简生成器（不支持 allOf/oneOf 等高级特性）。")
            return True, "builtin", warns
        except Exception as e:
            warns.append(f"内置生成器失败: {type(e).__name__}: {e}")
            return False, "builtin", warns





    @staticmethod
    def _summarize(report: dict[str, Any]) -> str:
        parts = [f"yaml: {report['yaml_path']}"]
        for lang in ("python", "typescript"):
            sec = report[lang]
            if not sec["attempted"]:
                continue
            tag = "✅" if sec.get("output") else "❌"
            gen = sec.get("generator") or "?"
            out = sec.get("output") or "(未生成)"
            parts.append(f"{tag} {lang} via {gen} → {out}")
            for w in sec.get("warnings", [])[:2]:
                parts.append(f"    ! {w}")
        return "\n".join(parts)

async def _run_cmd(cmd: list[str], *, timeout: float = 60) -> tuple[int, str, str]:

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (NotImplementedError, FileNotFoundError):

        joined = " ".join(_quote_arg(a) for a in cmd)
        proc = await asyncio.create_subprocess_shell(
            joined,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return 124, "", f"command timed out after {timeout}s"

    return (
        proc.returncode if proc.returncode is not None else -1,
        stdout_b.decode("utf-8", errors="replace"),
        stderr_b.decode("utf-8", errors="replace"),
    )

def _quote_arg(s: str) -> str:
    if not s or any(c in s for c in ' "\t'):
        return '"' + s.replace('"', '\\"') + '"'
    return s

_PY_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
}

_TS_TYPE_MAP = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
}

def _sanitize_name(name: str) -> str:
    n = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if n and n[0].isdigit():
        n = "_" + n
    return n or "Anonymous"

def _ref_name(ref: str) -> str:

    return _sanitize_name(ref.rsplit("/", 1)[-1])

def _builtin_pydantic(spec: dict) -> str:

    schemas = (spec.get("components") or {}).get("schemas") or {}
    lines: list[str] = [
        "# Auto-generated from contract.openapi.yaml by contract_codegen (builtin fallback)",
        "# 不支持 allOf / oneOf / anyOf 等高级特性；遇到会降级为 Any。",
        "from __future__ import annotations",
        "from typing import Any, List, Optional",
        "from pydantic import BaseModel, Field",
        "",
    ]



    for raw_name, sch in schemas.items():
        name = _sanitize_name(raw_name)
        if not isinstance(sch, dict):
            lines.append(f"# skipped {raw_name}: not an object")
            continue


        if "enum" in sch and sch.get("type") in (None, "string"):
            vals = sch["enum"]
            lines.append(f"class {name}(str):")
            lines.append(f"    # enum values")
            for v in vals:
                const = _sanitize_name(str(v)).upper()
                lines.append(f"    {const} = {v!r}")
            lines.append("")
            continue

        if sch.get("type") == "object" or "properties" in sch:
            required = set(sch.get("required") or [])
            lines.append(f"class {name}(BaseModel):")
            props = sch.get("properties") or {}
            if not props:
                lines.append("    pass")
                lines.append("")
                continue
            for field_name, prop in props.items():
                py_type = _openapi_to_py(prop)
                safe_field = _sanitize_name(field_name)
                default = "" if field_name in required else " = None"
                if field_name in required:
                    lines.append(f"    {safe_field}: {py_type}")
                else:
                    lines.append(f"    {safe_field}: Optional[{py_type}] = None")
            lines.append("")
        else:

            py_type = _openapi_to_py(sch)
            lines.append(f"{name} = {py_type}")
            lines.append("")

    return "\n".join(lines) + "\n"

def _openapi_to_py(prop: dict) -> str:
    if not isinstance(prop, dict):
        return "Any"
    if "$ref" in prop:
        return f'"{_ref_name(prop["$ref"])}"'
    if "allOf" in prop or "oneOf" in prop or "anyOf" in prop:
        return "Any"
    t = prop.get("type")
    if t == "array":
        items = prop.get("items") or {}
        return f"List[{_openapi_to_py(items)}]"
    if t in _PY_TYPE_MAP:
        return _PY_TYPE_MAP[t]
    if t == "object":
        return "dict[str, Any]"
    return "Any"

def _builtin_typescript(spec: dict) -> str:

    schemas = (spec.get("components") or {}).get("schemas") or {}
    lines: list[str] = [
        "// Auto-generated from contract.openapi.yaml by contract_codegen (builtin fallback)",
        "// 不支持 allOf / oneOf / anyOf 等高级特性；遇到会降级为 unknown。",
        "",
    ]
    for raw_name, sch in schemas.items():
        name = _sanitize_name(raw_name)
        if not isinstance(sch, dict):
            lines.append(f"// skipped {raw_name}")
            continue

        if "enum" in sch and sch.get("type") in (None, "string"):
            vals = sch["enum"]
            literal = " | ".join(json.dumps(v) for v in vals)
            lines.append(f"export type {name} = {literal};")
            lines.append("")
            continue

        if sch.get("type") == "object" or "properties" in sch:
            required = set(sch.get("required") or [])
            lines.append(f"export interface {name} {{")
            props = sch.get("properties") or {}
            for field_name, prop in props.items():
                ts_type = _openapi_to_ts(prop)
                opt = "" if field_name in required else "?"

                key = field_name if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", field_name) else json.dumps(field_name)
                lines.append(f"  {key}{opt}: {ts_type};")
            lines.append("}")
            lines.append("")
        else:
            ts_type = _openapi_to_ts(sch)
            lines.append(f"export type {name} = {ts_type};")
            lines.append("")

    return "\n".join(lines) + "\n"

def _openapi_to_ts(prop: dict) -> str:
    if not isinstance(prop, dict):
        return "unknown"
    if "$ref" in prop:
        return _ref_name(prop["$ref"])
    if "allOf" in prop or "oneOf" in prop or "anyOf" in prop:
        return "unknown"
    t = prop.get("type")
    if t == "array":
        items = prop.get("items") or {}
        return f"Array<{_openapi_to_ts(items)}>"
    if t in _TS_TYPE_MAP:
        return _TS_TYPE_MAP[t]
    if t == "object":
        return "Record<string, unknown>"
    return "unknown"
