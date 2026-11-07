"""YAML helpers that keep scientific-notation floats as strings.

Snakemake configurations carry parameters like ``1e-5`` that must reach the
rule unchanged.  PyYAML would turn them into ``float`` and reformat them, so
they load as strings; on dump the ``scn`` marker turns them back into a YAML
float.  This mirrors the loader used by SRPtn.
"""

from __future__ import annotations

import re
import yaml

SCIENTIFIC_FLOAT = re.compile(r"^\d+(\.\d+)?[eE][-+]?\d+$")


class CustomSafeLoader(yaml.SafeLoader):
    """Load scientific-notation floats as strings."""

    def scientificfloat_as_string(self, node: yaml.nodes.ScalarNode):
        value = self.construct_scalar(node)
        if SCIENTIFIC_FLOAT.match(value):
            return value
        return float(value)


CustomSafeLoader.add_constructor(
    "tag:yaml.org,2002:float", CustomSafeLoader.scientificfloat_as_string
)


class CustomSafeDumper(yaml.SafeDumper):
    """Dump ``scn``-marked strings as YAML floats."""

    def scientific_float(self, value: str):
        if re.match(r"^\d+(\.\d+)?[eE][-+]?\d+scn$", value):
            return self.represent_scalar("tag:yaml.org,2002:float", value[:-3])
        return self.represent_scalar("tag:yaml.org,2002:str", value)


CustomSafeDumper.add_representer(str, CustomSafeDumper.scientific_float)


def load(text: str, errors: list[str] | None = None):
    """Parse YAML, keeping scientific-notation floats as strings."""
    try:
        return yaml.load(text, Loader=CustomSafeLoader)
    except yaml.YAMLError as error:
        if errors is None:
            raise error
        errors.append(str(error))


def dump(data):
    """Serialize ``data`` without sorting keys."""
    return yaml.dump(data, sort_keys=False, Dumper=CustomSafeDumper)
