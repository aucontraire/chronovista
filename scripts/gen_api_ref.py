"""Generate the REST API Reference pages from the FastAPI OpenAPI schema.

Loads the live OpenAPI 3.1 document from ``chronovista.api.main.app`` and
writes one Markdown page per OpenAPI tag under ``reference/api/<tag>.md``, plus
an ``index.md`` overview and a ``SUMMARY.md`` literate-nav file. Executed at
build time by the ``gen-files`` mkdocs plugin.

The rendering is intentionally shallow: it references component schema names
(from ``$ref``) rather than fully expanding nested schemas, and links each
schema to its autodoc page under ``reference/code`` when a matching model
module exists. Every access is defensive (``.get(...)``) so a missing OpenAPI
key never breaks the build.
"""

from __future__ import annotations

import re
from typing import Any

import mkdocs_gen_files

from chronovista.api.main import app

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")


def _ref_name(ref: str) -> str:
    """Return the component name from a ``$ref`` like ``#/components/schemas/X``."""
    return ref.rsplit("/", 1)[-1] if ref else ""


def _schema_display(schema: dict[str, Any] | None) -> str:
    """Return a readable type/schema string for a JSON-schema fragment."""
    if not isinstance(schema, dict):
        return ""

    if "$ref" in schema:
        return f"`{_ref_name(schema['$ref'])}`"

    for combiner in ("allOf", "anyOf", "oneOf"):
        members = schema.get(combiner)
        if isinstance(members, list) and members:
            parts = [_schema_display(m) for m in members]
            parts = [p for p in parts if p and p != "`null`"]
            if parts:
                return " | ".join(dict.fromkeys(parts))

    schema_type = schema.get("type")
    if schema_type == "array":
        inner = _schema_display(schema.get("items"))
        return f"array of {inner}" if inner else "array"
    if schema_type:
        return f"`{schema_type}`"
    return ""


def _json_schema(container: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the ``application/json`` schema from a requestBody/response body."""
    if not isinstance(container, dict):
        return None
    content = container.get("content", {})
    if not isinstance(content, dict):
        return None
    media = content.get("application/json") or {}
    schema = media.get("schema")
    return schema if isinstance(schema, dict) else None


def _render_parameters(parameters: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    if not parameters:
        return lines
    lines.append("**Parameters**")
    lines.append("")
    lines.append("| Name | In | Type | Required | Description |")
    lines.append("| --- | --- | --- | --- | --- |")
    for param in parameters:
        if not isinstance(param, dict):
            continue
        name = param.get("name", "")
        location = param.get("in", "")
        type_str = _schema_display(param.get("schema")) or ""
        required = "yes" if param.get("required") else "no"
        description = (param.get("description") or "").replace("\n", " ").strip()
        lines.append(
            f"| `{name}` | {location} | {type_str} | {required} | {description} |"
        )
    lines.append("")
    return lines


def _render_request_body(request_body: dict[str, Any] | None) -> list[str]:
    lines: list[str] = []
    schema = _json_schema(request_body)
    if schema is None:
        return lines
    required = " (required)" if isinstance(request_body, dict) and request_body.get(
        "required"
    ) else ""
    lines.append("**Request body**" + required)
    lines.append("")
    display = _schema_display(schema) or "`object`"
    lines.append(f"- Body schema: {display}")
    lines.append("")
    return lines


def _render_responses(responses: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if not responses:
        return lines
    lines.append("**Responses**")
    lines.append("")
    lines.append("| Status | Description | Schema |")
    lines.append("| --- | --- | --- |")
    for status, response in sorted(responses.items()):
        if not isinstance(response, dict):
            continue
        description = (response.get("description") or "").replace("\n", " ").strip()
        schema = _json_schema(response)
        schema_str = _schema_display(schema) if schema is not None else ""
        lines.append(f"| `{status}` | {description} | {schema_str} |")
    lines.append("")
    return lines


_NUMPY_SECTION = re.compile(
    r"\n[ \t]*(?:Parameters|Returns|Yields|Raises|Examples?|Notes?|"
    r"See Also|Attributes|Warnings?)[ \t]*\n[ \t]*-{3,}"
)


def _clean_description(description: str) -> str:
    """Trim NumPy-style docstring sections from an operation description.

    FastAPI derives an operation's description from its route docstring, which
    often includes ``Parameters``/``Returns``/``Raises`` sections whose
    ``----------`` underline renders as a Markdown heading. The generated
    parameter/response tables already cover that, so keep only the prose before
    the first such section.
    """
    return _NUMPY_SECTION.split(description, maxsplit=1)[0].strip()


def _render_operation(method: str, path: str, op: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"## {method.upper()} {path}")
    lines.append("")

    summary = op.get("summary")
    if summary:
        lines.append(f"**{summary}**")
        lines.append("")

    description = op.get("description")
    if description:
        cleaned = _clean_description(description)
        if cleaned:
            lines.append(cleaned)
            lines.append("")

    operation_id = op.get("operationId")
    if operation_id:
        lines.append(f"`operationId`: `{operation_id}`")
        lines.append("")

    lines.extend(_render_parameters(op.get("parameters", []) or []))
    lines.extend(_render_request_body(op.get("requestBody")))
    lines.extend(_render_responses(op.get("responses", {}) or {}))
    return lines


def main() -> None:
    schema = app.openapi()
    paths: dict[str, Any] = schema.get("paths", {}) or {}

    # tag -> list of (path, method, operation)
    tag_ops: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, methods in sorted(paths.items()):
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            tags = op.get("tags") or ["untagged"]
            primary = tags[0]
            tag_ops.setdefault(primary, []).append((path, method, op))

    tags_sorted = sorted(tag_ops)

    # Per-tag pages
    for tag in tags_sorted:
        ops = sorted(tag_ops[tag], key=lambda item: (item[0], item[1]))
        lines: list[str] = [f"# API: {tag}", ""]
        lines.append(
            f"REST API operations tagged `{tag}` "
            f"({len(ops)} operation{'s' if len(ops) != 1 else ''})."
        )
        lines.append("")
        lines.append(
            "!!! info \"Generated page\"\n"
            "    Generated at build time from the FastAPI OpenAPI schema "
            "(`chronovista.api.main`)."
        )
        lines.append("")
        for path, method, op in ops:
            lines.extend(_render_operation(method, path, op))
        with mkdocs_gen_files.open(f"reference/api/{tag}.md", "w") as fd:
            fd.write("\n".join(lines))
        mkdocs_gen_files.set_edit_path(
            f"reference/api/{tag}.md", "src/chronovista/api/main.py"
        )

    # Overview index
    info = schema.get("info", {}) or {}
    index_lines: list[str] = ["# REST API Reference", ""]
    title = info.get("title")
    version = info.get("version")
    if title or version:
        index_lines.append(
            f"OpenAPI document for **{title or 'chronovista'}** "
            f"version `{version or 'unknown'}` "
            f"(OpenAPI `{schema.get('openapi', '3.1.0')}`)."
        )
        index_lines.append("")
    index_lines.append(
        f"The API exposes {len(paths)} paths across {len(tags_sorted)} tags. "
        "Each tag below has its own page listing every operation, its parameters, "
        "request body, and responses."
    )
    index_lines.append("")
    index_lines.append("| Tag | Operations |")
    index_lines.append("| --- | --- |")
    for tag in tags_sorted:
        count = len(tag_ops[tag])
        index_lines.append(f"| [{tag}]({tag}.md) | {count} |")
    index_lines.append("")
    with mkdocs_gen_files.open("reference/api/index.md", "w") as fd:
        fd.write("\n".join(index_lines))
    mkdocs_gen_files.set_edit_path(
        "reference/api/index.md", "src/chronovista/api/main.py"
    )

    # literate-nav SUMMARY for the API subtree
    summary_lines = ["* [Overview](index.md)"]
    for tag in tags_sorted:
        summary_lines.append(f"* [{tag}]({tag}.md)")
    with mkdocs_gen_files.open("reference/api/SUMMARY.md", "w") as fd:
        fd.write("\n".join(summary_lines) + "\n")


main()
