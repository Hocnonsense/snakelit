"""SRPtn scientific-float YAML codec with an error-collecting loader."""

import re

import yaml

SCIENTIFIC_FLOAT = re.compile(r"^\d+(\.\d+)?[eE][-+]?\d+$")


class CustomSafeLoader(yaml.SafeLoader):
    """Custom YAML loader."""

    def scientificfloat_as_string(
        self,
        node: yaml.nodes.ScalarNode,
    ):
        """Load scientific floats as strings if in scientific notation."""
        value = self.construct_scalar(node)
        # Check if the value looks like a float in scientific notation
        if SCIENTIFIC_FLOAT.match(value):
            return value
        return float(value)


CustomSafeLoader.add_constructor(
    "tag:yaml.org,2002:float", CustomSafeLoader.scientificfloat_as_string
)


class CustomSafeDumper(yaml.SafeDumper):
    """Custom YAML dumper."""

    def scientificfloat_from_string_as_float(
        self,
        value: str,
    ):
        """Dump scientific float from a string to yaml as float."""
        if re.match(r"^\d+(\.\d+)?[eE][-+]?\d+scn$", value):
            return self.represent_scalar(
                "tag:yaml.org,2002:float",
                value[:-3],  # Remove the custom 'scn' suffix and represent as float
            )
        return self.represent_scalar("tag:yaml.org,2002:str", value)


CustomSafeDumper.add_representer(
    str, CustomSafeDumper.scientificfloat_from_string_as_float
)


def load(text: str, errors: list[str] | None = None):
    """Parse YAML, keeping scientific-notation floats as strings."""
    try:
        return yaml.load(text, Loader=CustomSafeLoader)
    except yaml.YAMLError as error:
        if errors is None:
            raise
        errors.append(str(error))


def dump(data):
    """Dump YAML using the project dumper (keeps scientific floats as strings)."""
    return yaml.dump(data, sort_keys=False, Dumper=CustomSafeDumper)
