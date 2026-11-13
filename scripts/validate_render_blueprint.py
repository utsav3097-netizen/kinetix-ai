"""Validate the Render Blueprint against Render's published JSON Schema."""

import json
from pathlib import Path
from urllib.request import urlopen

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_URL = "https://render.com/schema/render.yaml.json"


def main() -> None:
    with urlopen(SCHEMA_URL, timeout=30) as response:
        schema = json.load(response)
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    errors = sorted(
        validator(schema).iter_errors(blueprint),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        for error in errors:
            path = "/".join(str(part) for part in error.absolute_path) or "<root>"
            print(f"{path}: {error.message}")
        raise SystemExit(f"render.yaml has {len(errors)} schema error(s)")
    print("render.yaml matches Render's published Blueprint schema")


if __name__ == "__main__":
    main()
