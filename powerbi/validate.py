"""Check the Power BI project before anyone opens it in Desktop.

1. Every JSON file is validated against the schema URL it declares, fetched from Microsoft.
2. Every table, column and measure a visual uses exists in the semantic model.
3. The TMDL files are indented with tabs only, as the format requires.
"""
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import certifi
from jsonschema import Draft7Validator, Draft202012Validator
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
_cache: dict[str, dict] = {}
_tls = ssl.create_default_context(cafile=certifi.where())


def fetch(uri: str) -> dict:
    if uri not in _cache:
        try:
            with urllib.request.urlopen(uri, timeout=30, context=_tls) as r:
                _cache[uri] = json.loads(r.read().decode("utf-8-sig"))
        except urllib.error.HTTPError as e:
            raise SystemExit(f"could not fetch schema {uri}: {e.code}") from e
    return _cache[uri]


def retrieve(uri: str) -> Resource:
    return Resource.from_contents(fetch(uri))


def schema_errors(path: Path) -> list[str]:
    doc = json.loads(path.read_text())
    uri = doc.get("$schema")
    if not uri:
        return [f"{path}: no $schema"]
    schema = fetch(uri)
    cls = Draft202012Validator if "2020-12" in schema.get("$schema", "") else Draft7Validator
    validator = cls(schema, registry=Registry(retrieve=retrieve))
    return [f"{path.relative_to(HERE)}: {'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in validator.iter_errors(doc)]


def model_fields() -> dict[str, set[str]]:
    fields: dict[str, set[str]] = {}
    for f in (HERE / "RetailSales.SemanticModel" / "definition" / "tables").glob("*.tmdl"):
        text = f.read_text()
        table = re.search(r"^table (.+)$", text, re.MULTILINE).group(1).strip("'")
        names = re.findall(r"^\t(?:column|measure) ('[^']+'|\S+)", text, re.MULTILINE)
        fields[table] = {n.strip("'") for n in names}
    return fields


def reference_errors(fields: dict[str, set[str]]) -> list[str]:
    errors = []
    for vf in (HERE / "RetailSales.Report").rglob("visual.json"):
        for entity, prop in re.findall(r'"Entity": "([^"]+)"\s*\}\s*\},\s*"Property": "([^"]+)"', vf.read_text()):
            if prop not in fields.get(entity, set()):
                errors.append(f"{vf.relative_to(HERE)}: {entity}[{prop}] is not in the model")
    return errors


def tmdl_errors() -> list[str]:
    errors = []
    for f in (HERE / "RetailSales.SemanticModel" / "definition").rglob("*.tmdl"):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            indent = line[: len(line) - len(line.lstrip(" \t"))]
            # TMDL structure is tabs. Inside an M expression, spaces after the tabs belong to M.
            if indent.startswith(" "):
                errors.append(f"{f.relative_to(HERE)}:{n}: indentation starts with a space")
    return errors


def main() -> None:
    errors = []
    files = [*HERE.glob("*.pbip"), *(HERE / "RetailSales.Report").rglob("*.json"),
             *(HERE / "RetailSales.Report").glob("*.pbir"), *(HERE / "RetailSales.SemanticModel").glob("*.pbism")]
    files = [f for f in files if "StaticResources" not in f.parts]
    for f in sorted(files):
        errors += schema_errors(f)
    fields = model_fields()
    errors += reference_errors(fields)
    errors += tmdl_errors()
    print(f"{len(files)} JSON files checked against their schemas; {sum(len(v) for v in fields.values())} model fields")
    print("\n".join(errors) or "no problems found")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
