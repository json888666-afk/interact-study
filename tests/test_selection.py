from backend.selection import sample_candidates


class ReverseRng:
    def shuffle(self, items):
        items.reverse()


def test_sample_candidates_keeps_all_when_below_limit():
    assert sample_candidates([1, 2, 3], limit=16, rng=ReverseRng()) == [3, 2, 1]


def test_sample_candidates_shuffles_then_caps():
    result = sample_candidates(list(range(20)), limit=16, rng=ReverseRng())
    assert result == list(range(19, 3, -1))
    assert len(result) == 16 and len(set(result)) == 16


def test_sample_candidates_handles_empty_input():
    assert sample_candidates([], rng=ReverseRng()) == []
