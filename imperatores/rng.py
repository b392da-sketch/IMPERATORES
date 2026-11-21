"""Random streams keyed by system and stable identity.

Each (stream, key) pair has its own generator, derived from the run seed. Keys are stable
identities (entity ids from the scenario file, later order or occurrence ids), never list
positions. A change to one entity, order or decision therefore cannot shift another
entity's random draws, which is what makes paired-seed intervention tests possible
(specification 6 and 7.1).

Key encoding (schema 1): spawn_key = (KEY_SCHEMA, stream index, number of key parts, *parts),
every part an int in [0, 2**32). The length prefix and the fixed 32-bit range keep the
boundaries between parts unambiguous, so distinct keys can never produce the same stream
(Codex review 002, finding 2).
"""
from __future__ import annotations

import numpy as np

KEY_SCHEMA = 1
_U32 = 2 ** 32

# Append new streams at the end; never insert or reorder (it would change every run).
STREAMS = ["movement"]


def _check_part(x) -> int:
    if isinstance(x, bool) or not isinstance(x, (int, np.integer)):
        raise TypeError(f"random key parts must be integers, not {type(x).__name__}")
    x = int(x)
    if not (0 <= x < _U32):
        raise ValueError(f"random key part {x} outside [0, 2**32)")
    return x


class Random:
    def __init__(self, seed: int):
        self.seed = _check_part(seed)
        self._gens: dict[tuple, np.random.Generator] = {}

    def gen(self, stream: str, *key: int) -> np.random.Generator:
        """Generator for one stream and key (usually a stable entity id). Created on first use."""
        if stream not in STREAMS:
            raise ValueError(f"unknown random stream {stream!r}")
        parts = tuple(_check_part(x) for x in key)
        k = (stream,) + parts
        g = self._gens.get(k)
        if g is None:
            spawn = (KEY_SCHEMA, STREAMS.index(stream), len(parts)) + parts
            g = np.random.default_rng(np.random.SeedSequence(self.seed, spawn_key=spawn))
            self._gens[k] = g
        return g
