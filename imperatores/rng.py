"""Random streams keyed by system and entity.

Each (stream, key) pair has its own generator, derived from the run seed. A change to
one entity, order or decision therefore never shifts another entity's random draws,
which is what makes paired-seed intervention tests possible (specification 6 and 7.1).
"""
from __future__ import annotations

import numpy as np

# Append new streams at the end; never insert or reorder (it would change every run).
STREAMS = ["movement"]


class Random:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self._gens: dict[tuple, np.random.Generator] = {}

    def gen(self, stream: str, *key: int) -> np.random.Generator:
        """Generator for one stream and key (usually an entity id). Created on first use."""
        k = (stream,) + tuple(int(x) for x in key)
        g = self._gens.get(k)
        if g is None:
            idx = STREAMS.index(stream)          # KeyError-like ValueError for an unknown stream
            ss = np.random.SeedSequence(self.seed, spawn_key=(idx,) + k[1:])
            g = np.random.default_rng(ss)
            self._gens[k] = g
        return g
