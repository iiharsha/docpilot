"""Reciprocal Rank Fusion: several rankings of the same items, merged by rank alone.

An item scores `weight / (k + rank)` in each ranking it appears in, ranks
counting from 1, and the scores add up. Only positions count, so a cosine
distance and a `ts_rank_cd` score, which share no scale, can still be fused.
The larger `k`, the less the top few places of any one ranking outweigh
agreement between rankings; 60 is the value Cormack, Clarke and Büttcher
(2009) found robust.
"""

from collections.abc import Hashable, Sequence

K = 60


def fuse[T: Hashable](
    rankings: Sequence[Sequence[T]], weights: Sequence[float], k: int = K
) -> list[T]:
    """Every item in any ranking, best first.

    Ties keep the order the items were first seen in, so the result is stable
    for a given input.
    """
    scores: dict[T, float] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
    return sorted(scores, key=scores.__getitem__, reverse=True)
