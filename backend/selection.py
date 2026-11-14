import random

RNG = random.SystemRandom()
CANDIDATE_LIMIT = 16


def sample_candidates(items, limit=CANDIDATE_LIMIT, rng=RNG):
    values = list(items)
    rng.shuffle(values)
    return values[:limit]
