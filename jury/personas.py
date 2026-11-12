"""Load persona YAML files."""

from pathlib import Path

import yaml

from jury.models import Persona

PERSONA_DIR = Path(__file__).resolve().parent.parent / "personas"


def load_persona(persona_id: str, directory: Path = PERSONA_DIR) -> Persona:
    path = directory / f"{persona_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no persona file: {path}")
    return Persona.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_all(directory: Path = PERSONA_DIR) -> dict[str, Persona]:
    return {p.stem: load_persona(p.stem, directory) for p in sorted(directory.glob("*.yaml"))}
