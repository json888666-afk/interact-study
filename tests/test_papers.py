import base64
import io
import json
import zipfile
from uuid import uuid4
from xml.sax.saxutils import escape

import pytest
from PIL import Image, ImageDraw

from backend.exams import EXAM_SELECT_PROMPT
from backend.paper_files import Page, read_files
from backend.paper_store import matching_questions
from backend.papers import (
    IMPORT_PROMPT, IMPORT_VERIFY_PROMPT, REGION_PROMPT, REGION_VERIFY_PROMPT, RETRY_PROMPT, RETRY_VERIFY_PROMPT,
    PaperReading, reconcile,
)
from backend.quiz_models import DRAFT_PROMPT, FIRST_REVIEW_PROMPT
from backend.quiz_store import database
from test_learning_quiz import client, context, mock_upstream, question

EXAM = {"exam": "成都市数学中考", "subject": "数学"}
STEM = "二次函数的图像开口向上时，二次项系数满足什么条件？"
OPTIONS = ["大于零", "小于零", "等于零"]
SECOND = "描述二次函数顶点与对称轴的关系。"
PASSWORD = "Paper-only-42"


def document(*lines):
    xml = '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    xml += "".join(f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in lines)
    xml += "</w:body></w:document>"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return stream.getvalue()


def upload(client, filename, data, consent=True, exam="成都中考数学"):
    return client.post("/api/exam-library/imports", json={
        "exam": exam, "subject": "数学", "year": 2025, "paper": "A卷", "consent": consent,
        "files": [{"filename": filename, "data": base64.b64encode(data).decode()}],
    })


def register(client, name, goal="备考成都市数学中考"):
    response = client.post("/api/auth/register", json={
        "username": name, "password": PASSWORD,
        "profile": {"education_stage": "初中", "goal": goal},
    })
    assert response.status_code == 201


@pytest.fixture
def importer(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    monkeypatch.setenv("EXAM_QUIZ_MODE", "debug")
    state = {"prompts": [], "conflict": False}

    def handler(prompt, content, _model):
        state["prompts"].append(prompt)
        if prompt in {IMPORT_PROMPT, IMPORT_VERIFY_PROMPT}:
            answer = "B" if state["conflict"] and prompt == IMPORT_VERIFY_PROMPT else "A"
            return {"questions": [
                {"page": 1, "number": "1", "stem": STEM, "tags": ["二次函数", "开口方向"],
                 "options": [{"label": label, "text": text} for label, text in zip("ABC", OPTIONS)]},
                {"page": 1, "number": "2", "stem": SECOND, "tags": ["二次函数", "对称轴"]},
            ], "answers": [{"page": 1, "number": "1", "choices": [answer], "evidence": f"1. {answer}"}]}
        data = json.loads(content)
        if prompt == EXAM_SELECT_PROMPT:
            assert len(data["candidates"]) == 1
            assert data["candidates"][0]["stem"] == STEM
            return {"questions": [{"candidate": 0, "topic": "二次函数", "correct": [0], "explanation": "二次项系数为正。"}]}
        if prompt == DRAFT_PROMPT:
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    def inspect(request):
        assert request.url.path.endswith("/chat/completions"), "有匹配本地题时不应调用联网搜索"

    mock_upstream(handler, inspect_request=inspect,
                  goal_handler=lambda _data: {"verdict": "approved", "message": "通过", "exam": EXAM})
    return state


def test_import_word_deduplicates_and_uses_private_bank_in_practice(client, importer):
    data = document("1. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)),
                    "2. " + SECOND, "参考答案", "1. A")
    assert upload(client, "paper.docx", data).status_code == 401
    register(client, "PaperUser")
    assert upload(client, "paper.docx", data, consent=False).status_code == 422
    response = upload(client, "paper.docx", data)
    assert response.status_code == 201, response.text
    paper = response.json()["paper"]
    assert (paper["question_count"], paper["ready_count"]) == (2, 1)
    assert paper["questions"][1]["kind"] == "other"
    assert upload(client, "paper.docx", data).json()["duplicate"]
    assert importer["prompts"].count(IMPORT_PROMPT) == 1

    headers = {"X-Study-Session": str(uuid4())}
    material = context(client) | {"version_id": str(uuid4())}
    created = client.post("/api/quizzes", headers=headers, json=material)
    quiz_path = "/api/quizzes/" + created.json()["id"]
    quiz = client.get(quiz_path, headers=headers).json()
    assert quiz["status"] == "ready", quiz["message"]
    imported = quiz["questions"][0]
    assert imported["origin"] == "past" and imported["source"]["imported"]
    assert imported["source"]["filename"] == "paper.docx" and "answer" not in imported
    assert quiz["questions"][1]["origin"] == "simulated"
    assert client.post(f"{quiz_path}/questions/{imported['id']}/answer", headers=headers,
                       json={"selected": [0]}).json()["questions"][0]["answer"]["is_correct"]

    register(client, "AnotherPaperUser")
    path = f"/api/exam-library/{paper['id']}"
    assert client.get(path).status_code == 404 and client.post(path + "/delete").status_code == 404
    assert client.get("/api/exam-library").json()["papers"] == []
    client.post("/api/auth/login", json={"username": "PaperUser", "password": PASSWORD})
    assert client.post(path + "/delete").status_code == 200
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(("filename", "format_name", "conflict"), [("paper.pdf", "PDF", False), ("paper.png", "PNG", True)])
def test_scans_and_photos_use_two_reads_before_automatic_grading(client, importer, filename, format_name, conflict):
    register(client, "PaperUser")
    stream = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(stream, format=format_name)
    assert read_files([(filename, stream.getvalue())])[0].images
    importer["conflict"] = conflict
    response = upload(client, filename, stream.getvalue())
    assert response.status_code == 201, response.text
    assert importer["prompts"] == [IMPORT_PROMPT, IMPORT_VERIFY_PROMPT]
    assert response.json()["paper"]["ready_count"] == (0 if conflict else 1)


def test_wrong_printed_question_number_cannot_be_used_for_grading(client, importer):
    register(client, "PaperUser")
    data = document("9. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)), "参考答案", "1. A")
    response = upload(client, "paper.docx", data)
    assert response.status_code == 201
    assert response.json()["paper"]["ready_count"] == 0


def test_multicolumn_photo_rescan_and_targeted_retry(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    stream = io.BytesIO()
    image = Image.new("RGB", (1600, 2800), "white")
    draw = ImageDraw.Draw(image)
    draw.text((120, 220), "1. Find the quadratic coefficient.", fill="black")
    draw.text((920, 220), "2. Explain the axis of symmetry.", fill="black")
    draw.text((920, 1800), "3. [obscured formula]", fill="gray")
    image.save(stream, format="PNG")
    data = stream.getvalue()
    page = read_files([("two-columns.png", data)])[0]
    assert any(box[0] > 0 for box, _ in page.regions)
    assert any(top < 500 < bottom for (_, top, _, bottom), _ in page.regions)

    state = {"rescan": False, "correct_retry": False}

    def extracted(number, stem, **kwargs):
        return {"page": 1, "number": str(number), "stem": stem, "tags": ["二次函数"], **kwargs}

    def with_options(number, stem):
        return extracted(number, stem, options=[{"label": k, "text": v} for k, v in zip("ABC", OPTIONS)])

    def answer(number, page=1):
        return {"page": page, "number": str(number), "choices": ["A"], "evidence": f"{number}. A"}

    def handler(prompt, content, _model):
        if prompt in {IMPORT_PROMPT, IMPORT_VERIFY_PROMPT}:
            return {"questions": [with_options(1, STEM)], "answers": [answer(1)], "columns": 2,
                    "located": [{"page": 1, "number": str(n)} for n in ([1, 3] if not state["rescan"] else [1, 2, 3, 4])]}
        if prompt in {REGION_PROMPT, REGION_VERIFY_PROMPT}:
            region = content[0]["text"]
            if "(440, 0," in region:
                return {"questions": [extracted(2, SECOND)], "answers": []}
            if "(440," in region and "(440, 0," not in region:
                third = with_options(3, "二次函数的二次项系数是 2 还是 3？" if prompt == REGION_PROMPT else "二次函数的二次项系数是 2 还是 8？")
                return {"questions": [third, *([extracted(4, "说明抛物线的平移规律。")] if state["rescan"] else [])],
                        "answers": []}
            return {"questions": [], "answers": []}
        assert prompt in {RETRY_PROMPT, RETRY_VERIFY_PROMPT}
        assert "指定题号 3" in content[0]["text"]
        number = 3 if state["correct_retry"] else 4
        return {"questions": [with_options(number, "二次函数 y=2x² 的系数符号是什么？")], "answers": [answer(number, 2)]}

    mock_upstream(handler)
    register(client, "PhotoUser")
    initial = upload(client, "two-columns.png", data)
    assert initial.status_code == 201, initial.text
    paper = initial.json()["paper"]
    assert (paper["ready_count"], paper["review_count"], paper["pending_count"]) == (1, 1, 1)
    assert [q["number"] for q in paper["questions"]] == ["1", "2", "3"]
    assert "不一致" in paper["questions"][2]["reason"]
    assert upload(client, "two-columns.png", data).json()["duplicate"]

    path = "/api/exam-library/" + paper["id"]
    files = [{"filename": "two-columns.png", "data": base64.b64encode(data).decode()}]
    state["rescan"] = True
    for _ in range(2):
        result = client.post(path + "/reprocess", json={"consent": True, "files": files})
        assert result.status_code == 200, result.text
        assert [q["number"] for q in result.json()["paper"]["questions"]] == ["1", "2", "3", "4"]
    assert result.json()["paper"]["questions"][:3] == paper["questions"]
    pending = paper["questions"][2]
    retry = f"{path}/questions/{pending['id']}/retry"
    retry_files = [files[0] | {"filename": "question.png"}, files[0] | {"filename": "answer.png"}]
    assert client.post(retry, json={"consent": True, "files": retry_files}).status_code == 422
    state["correct_retry"] = True
    updated = client.post(retry, json={"consent": True, "files": retry_files})
    assert updated.status_code == 200, updated.text
    final = updated.json()["paper"]
    assert final["questions"][2]["id"] == pending["id"]
    assert (final["ready_count"], final["review_count"], final["pending_count"]) == (2, 2, 0)
    assert final["questions"][:2] == paper["questions"][:2]
    assert "correct" not in final["questions"][2]
    with database() as connection:
        account = connection.execute("SELECT account_id FROM imported_papers WHERE id = ?", (paper["id"],)).fetchone()
        rows = matching_questions(connection, account[0], "二次函数")
    assert {json.loads(row["data"])["number"] for row in rows} == {"1", "3"}


def test_same_number_in_different_sections_and_pages_is_not_merged():
    pages = [Page("paper.pdf", 1), Page("paper.pdf", 2)]
    first = PaperReading.model_validate({
        "located": [{"page": 1, "number": "1", "section": "B卷"}, {"page": 1, "number": "1", "section": "A卷"}],
        "questions": [
            {"page": page, "number": number, "section": section, "stem": stem, "tags": ["二次函数"],
             "options": [{"label": k, "text": v} for k, v in zip("ABC", OPTIONS)]}
            for page, number, section, stem in [(1, "A卷1", None, STEM), (1, "1", "B卷", SECOND), (2, "1", None, STEM)]
        ],
        "answers": [{"page": 1, "number": "1", "choices": ["A"], "evidence": "1. A"}],
    })
    output = reconcile(pages, [([1, 2], first, first)])
    assert [(q["page"], q["section"], q["number"]) for q in output] == [(1, "B卷", "1"), (1, "A卷", "1"), (2, None, "1")]
    assert all(q["status"] == "review_only" for q in output)


def test_knowledge_target_matches_bank_across_exams_but_exam_target_does_not(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    beijing = STEM + "（北京）"
    chengdu = STEM + "（成都）"
    expected = {"exam": None, "stem": beijing}

    def handler(prompt, content, _model):
        data = json.loads(content) if isinstance(content, str) and content.startswith("{") else content
        if prompt == IMPORT_PROMPT:
            stem = beijing if beijing in content[0]["text"] else chengdu
            return {"questions": [{"page": 1, "number": "1", "stem": stem, "tags": ["二次函数"],
                                   "options": [{"label": k, "text": v} for k, v in zip("ABC", OPTIONS)]}],
                    "answers": [{"page": 1, "number": "1", "choices": ["A"], "evidence": "1. A"}]}
        if prompt == EXAM_SELECT_PROMPT:
            assert data["context"]["exam"] == expected["exam"]
            assert {item["stem"] for item in data["candidates"]} == ({chengdu} if expected["exam"] else {beijing, chengdu})
            idx = next(i for i, item in enumerate(data["candidates"]) if item["stem"] == expected["stem"])
            return {"questions": [{"candidate": idx, "topic": "二次函数", "correct": [0], "explanation": "系数为正。"}]}
        if prompt == DRAFT_PROMPT:
            assert data["scope"]["count"] == 1
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    def check_request(request):
        assert request.url.path.endswith("/chat/completions")

    mock_upstream(handler, inspect_request=check_request, goal_handler=lambda data: {
        "verdict": "approved", "message": "通过", "exam": EXAM if "中考" in data["goal"] else None,
    })
    register(client, "CrossExamUser", "学懂二次函数")
    for exam, stem in [("成都中考数学", chengdu), ("北京中考数学", beijing)]:
        body = document("1. " + stem, *(f"{k}. {v}" for k, v in zip("ABC", OPTIONS)), "参考答案", "1. A")
        assert upload(client, "original.docx", body, exam=exam).status_code == 201

    def make_quiz():
        headers = {"X-Study-Session": str(uuid4())}
        material = context(client) | {"version_id": str(uuid4())}
        created = client.post("/api/quizzes", headers=headers, json=material)
        return client.get("/api/quizzes/" + created.json()["id"], headers=headers).json()

    quiz = make_quiz()
    assert quiz["status"] == "ready" and quiz["questions"][0]["source"]["exam"] == "北京中考数学"
    assert "exam" not in quiz
    update = client.post("/api/auth/profile", json={"education_stage": "初中", "goal": "备考成都中考数学"})
    assert update.status_code == 200
    expected.update(exam=EXAM, stem=chengdu)
    quiz = make_quiz()
    assert quiz["status"] == "ready" and quiz["questions"][0]["source"]["exam"] == "成都中考数学"
