"""Containers whose repr shows shape only, so pytest failure output never prints values."""


class KeysOnly(dict):
    """A settings mapping; repr lists key names (nested mappings are wrapped too)."""

    def __init__(self, data=()):
        super().__init__({k: KeysOnly(v) if isinstance(v, dict) else v for k, v in dict(data).items()})

    def __repr__(self) -> str:
        return f"KeysOnly({sorted(self)})"


class Bodies(list):
    """Raw OTLP request bodies (identifiers, content); repr gives the count only."""

    def __repr__(self) -> str:
        return f"<{len(self)} request bodies>"
