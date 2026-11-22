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
STREAMS = ["movement", "perception", "messengers", "signals", "decisions"]


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


# ---- counter-based keyed draws -------------------------------------------------------------
# For draws needed in bulk (for example one per observer-target pair per perception cycle),
# a generator per key would be wasteful. These draws are a pure function of
# (seed, stream, key parts, draw number), computed with the SplitMix64 mixer: no state, so
# they are independent of call order and of whatever else is drawn in the same call.
# Schema 1; change the schema number if the construction ever changes.
#
# Collision risk (Codex review 004): keys are mixed into a 64-bit state, so two distinct keys
# can in principle share a state. For n distinct keys the chance of any collision is about
# n**2 / 2**65; for a full battle (about 10**8 keyed sightings) that is below 10**-3, and a
# collision would only make two sightings' errors equal, not leak information.

_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)
_GOLDEN = np.uint64(0x9E3779B97F4A7C15)


def _mix(x: np.ndarray) -> np.ndarray:
    x = x ^ (x >> np.uint64(30))
    x = x * _M1
    x = x ^ (x >> np.uint64(27))
    x = x * _M2
    return x ^ (x >> np.uint64(31))


def keyed_uniforms(seed: int, stream: str, keys: list, n_draws: int) -> np.ndarray:
    """Uniforms in [0, 1), shape (*broadcast(keys), n_draws). Each key part: int array in [0, 2**32)."""
    if stream not in STREAMS:
        raise ValueError(f"unknown random stream {stream!r}")
    with np.errstate(over="ignore"):
        h = _mix(np.uint64(_check_part(seed)) ^ np.uint64(KEY_SCHEMA << 32) ^ _GOLDEN)
        h = _mix(h ^ np.uint64(STREAMS.index(stream) + 1) * _GOLDEN)
        for part in keys:
            a = np.asarray(part)
            if a.dtype.kind not in "iu" or (a.size and (a.min() < 0 or a.max() >= _U32)):
                raise ValueError("keyed draw parts must be integers in [0, 2**32)")
            h = _mix(h ^ (a.astype(np.uint64) + np.uint64(1)) * _GOLDEN)
        j = np.arange(1, n_draws + 1, dtype=np.uint64)
        out = _mix(h[..., None] ^ (j * _GOLDEN))
    # (k + 0.5) / 2**53: strictly inside (0, 1), so Box-Muller never needs a floor on log(u)
    return ((out >> np.uint64(11)).astype(np.float64) + 0.5) * (1.0 / 9007199254740992.0)


def keyed_normals(seed: int, stream: str, keys: list, n_draws: int) -> np.ndarray:
    """Standard normal draws (Box-Muller), shape (*broadcast(keys), n_draws)."""
    u = keyed_uniforms(seed, stream, keys, 2 * n_draws)
    u1 = u[..., 0::2]
    u2 = u[..., 1::2]
    return np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)
