
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from qmap.exceptions import ConfigurationError

__all__ = ["DEFAULT_SEED", "SeedSequence"]

DEFAULT_SEED = 20260519

_HASH_BYTES = 8
"""Bytes of BLAKE2b digest folded into each derived seed (64 bits)."""

def _derive(root: int, label: str) -> int:
    payload = f"{root}\x00{label}".encode()
    digest = hashlib.blake2b(payload, digest_size=_HASH_BYTES).digest()
    return int.from_bytes(digest, byteorder="big")

@dataclass(frozen=True, slots=True)
class SeedSequence:

    seed: int
    path: str

    @classmethod
    def from_seed(cls, seed: int | None = None) -> SeedSequence:
        if seed is None:
            seed = DEFAULT_SEED
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ConfigurationError(f"seed must be an integer, got {type(seed).__name__}")
        if seed < 0:
            raise ConfigurationError(f"seed must be non-negative, got {seed}")
        return cls(seed=seed, path=str(seed))

    def stream(self, label: str) -> SeedSequence:
        if not label:
            raise ConfigurationError("stream label must be a non-empty string")
        return SeedSequence(seed=_derive(self.seed, label), path=f"{self.path}.{label}")

    def for_trial(self, *components: Any) -> SeedSequence:
        if not components:
            raise ConfigurationError("for_trial requires at least one component")
        return self.stream(".".join(str(c) for c in components))

    def generator(self) -> np.random.Generator:
        return np.random.default_rng(self.seed)

    def __str__(self) -> str:
        return self.path
