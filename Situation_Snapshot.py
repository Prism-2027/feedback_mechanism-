import argparse
import json
from pathlib import Path
from typing import Any


TEMPLATE_PATH = Path(__file__).with_name("Situation_Snapshot.json")


def _check_shape(template: Any, value: Any, path: str = "$") -> None:
    if isinstance(template, dict):
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")

        missing = template.keys() - value.keys()
        extra = value.keys() - template.keys()
        if missing:
            raise ValueError(f"{path} is missing keys: {', '.join(sorted(missing))}")
        if extra:
            raise ValueError(f"{path} has unexpected keys: {', '.join(sorted(extra))}")

        for key, child_template in template.items():
            _check_shape(child_template, value[key], f"{path}.{key}")
        return

    if isinstance(template, list):
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        if template:
            for index, item in enumerate(value):
                _check_shape(template[0], item, f"{path}[{index}]")
        return

    if template is None:
        return

    if type(value) is not type(template):
        raise ValueError(f"{path} must be {type(template).__name__}")


def validate_snapshot(data: Any) -> None:
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    _check_shape(template, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Situation Snapshot JSON file.")
    parser.add_argument("snapshot", type=Path, help="Path to the JSON file to validate")
    args = parser.parse_args()

    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    validate_snapshot(data)
    print(f"{args.snapshot} matches the Situation Snapshot format.")


if __name__ == "__main__":
    main()
