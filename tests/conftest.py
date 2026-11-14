from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture(autouse=True)
def quiz_database(monkeypatch):
    root = Path(__file__).resolve().parents[1] / ".local"
    root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="quiz-test-", dir=root) as directory:
        path = Path(directory) / "quiz.sqlite3"
        monkeypatch.setenv("QUIZ_DB_PATH", str(path))
        yield path


@pytest.fixture(autouse=True)
def stable_candidate_sampling(monkeypatch):
    monkeypatch.setattr("backend.exams.sample_candidates", lambda items, limit=16: list(items)[:limit])
