"""Decode finite-analysis requests, rejecting ambiguous duplicate fields."""
import json

from .types import BError


MAX_REQUEST_BYTES = 64 * 1024


def decode(text, error_code):
    def object_from_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise BError(error_code, f"Duplicate JSON key {key!r}")
            obj[key] = value
        return obj
    try:
        return json.loads(text, object_pairs_hook=object_from_pairs)
    except (ValueError, RecursionError) as exc:
        raise BError(error_code, f"Invalid JSON: {exc}") from exc
