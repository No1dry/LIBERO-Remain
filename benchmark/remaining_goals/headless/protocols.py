"""Pure, fixed protocol identities; arbitrary source masks are never accepted."""
from dataclasses import dataclass

LEGACY_PROTOCOL = "mask10"
NORMAL00_PROTOCOL = "normal00-control"
NORMAL00_VERSION = "remaining-headless-normal00-control-v1"
NORMAL00_RESULT_SCHEMA = "remaining-headless-normal00-episode-v1"


@dataclass(frozen=True)
class Protocol:
    key: str
    protocol_version: str
    result_schema: str
    config_schema: str
    plan_schema: str
    source_acceptance_schema: str
    initial_mask: tuple
    preserved_goal_indices: tuple
    summary_schema: str
    horizon: int = 520
    confirmation_steps: int = 4
    max_chunk_steps: int = 8

    def validate_mask(self, mask):
        if (not isinstance(mask, list) or len(mask) != 2 or
                any(type(item) is not bool for item in mask) or tuple(mask) != self.initial_mask):
            raise ValueError(f"{self.key} requires exactly source mask{''.join(str(int(x)) for x in self.initial_mask)}")

    def validate_identity(self, identity):
        if identity is None:
            return
        if not isinstance(identity, dict):
            raise ValueError("protocol identity must be an object")
        version = identity.get("protocol_version")
        if version is not None and version != self.protocol_version:
            raise ValueError("run identity protocol differs from execution protocol")
        if self.key == NORMAL00_PROTOCOL and version != self.protocol_version:
            raise ValueError("normal00 run identity requires explicit protocol_version")
        if self.key == NORMAL00_PROTOCOL and "source_acceptance" in identity:
            acceptance = identity["source_acceptance"]
            if not isinstance(acceptance, dict) or acceptance.get("schema_version") != self.source_acceptance_schema:
                raise ValueError("normal00 source acceptance schema differs from protocol")
        if "protocol" in identity and identity["protocol"] != self.key:
            raise ValueError("run identity protocol key differs from execution protocol")


_PROTOCOLS = {
    LEGACY_PROTOCOL: Protocol(LEGACY_PROTOCOL, "remaining-headless-goal-endpoint-v1",
        "remaining-headless-episode-v1", "remaining-headless-batch-config-v1",
        "remaining-headless-batch-plan-v1", "remaining-headless-mask10-source-acceptance-v1",
        (True, False), (0,), "remaining-headless-summary-v1"),
    NORMAL00_PROTOCOL: Protocol(NORMAL00_PROTOCOL, NORMAL00_VERSION, NORMAL00_RESULT_SCHEMA,
        "remaining-headless-normal00-batch-config-v1", "remaining-headless-normal00-batch-plan-v1",
        "remaining-headless-normal00-source-acceptance-v1", (False, False), (),
        "remaining-headless-normal00-summary-v1"),
}


def get_protocol(key=LEGACY_PROTOCOL):
    if not isinstance(key, str) or key not in _PROTOCOLS:
        raise ValueError(f"unsupported headless protocol: {key!r}")
    return _PROTOCOLS[key]


def protocol_for_result(result):
    """Dispatch only an exact version/schema pair, never the mask alone."""
    if not isinstance(result, dict):
        raise ValueError("headless result must be an object")
    for descriptor in _PROTOCOLS.values():
        if (result.get("protocol_version") == descriptor.protocol_version and
                result.get("schema_version") == descriptor.result_schema):
            return descriptor
    raise ValueError("incompatible headless result schema/protocol")
