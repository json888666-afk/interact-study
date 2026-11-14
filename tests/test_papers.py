import asyncio
import base64
import io
import json
import zipfile
from types import SimpleNamespace
from uuid import uuid4
from xml.sax.saxutils import escape

import httpx
import pytest
from PIL import Image, ImageDraw

from backend import paper_store as store
from backend.exams import EXAM_SELECT_PROMPT, SELECT_OPEN_PROMPT, ExamUnavailable
from backend.model import ModelSettings
from backend.paper_files import Page, read_files
from backend.paper_store import matching_questions
from backend.papers import IMPORT_PROMPT, RETRY_PROMPT, PaperReading, draft_questions
from backend.quiz_models import CONVERT_TO_CHOICE_PROMPT, DRAFT_PROMPT, FIRST_REVIEW_PROMPT, convert_to_choice
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


def with_options(number, stem):
    return {"page": 1, "number": str(number), "stem": stem, "tags": ["二次函数"],
            "options": [{"label": label, "text": text} for label, text in zip("ABC", OPTIONS)]}


@pytest.fixture
def importer(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    monkeypatch.setenv("EXAM_QUIZ_MODE", "debug")
    state = {"prompts": []}

    def handler(prompt, content, _model):
        state["prompts"].append(prompt)
        if prompt == IMPORT_PROMPT:
            return {"questions": [with_options(1, STEM), {"page": 1, "number": "2", "stem": SECOND,
                                                          "tags": ["二次函数", "对称轴"]}],
                    "answers": [{"page": 1, "number": "1", "choices": ["A"], "evidence": "1. A"}]}
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
    assert (paper["question_count"], paper["draft_count"]) == (2, 2)
    assert paper["ready_count"] == 0 and paper["confirmed_count"] == 0
    assert [item["status"] for item in paper["questions"]] == ["draft", "draft"]
    assert upload(client, "paper.docx", data).json()["duplicate"]
    assert importer["prompts"].count(IMPORT_PROMPT) == 1

    with database() as connection:
        account = connection.execute("SELECT account_id FROM imported_papers WHERE id = ?", (paper["id"],)).fetchone()
        assert matching_questions(connection, account[0], "二次函数") == []

    headers = {"X-Study-Session": str(uuid4())}

    def make_quiz():
        material = context(client) | {"version_id": str(uuid4())}
        created = client.post("/api/quizzes", headers=headers, json=material)
        path = "/api/quizzes/" + created.json()["id"]
        return path, client.get(path, headers=headers).json()

    first = paper["questions"][0]
    confirmed = client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["paper"]["ready_count"] == 1

    path, quiz = make_quiz()
    assert quiz["status"] == "ready", quiz["message"]
    imported = quiz["questions"][0]
    assert imported["origin"] == "past" and imported["source"]["imported"]
    assert imported["source"]["filename"] == "paper.docx" and "answer" not in imported
    assert client.post(f"{path}/questions/{imported['id']}/answer", headers=headers,
                       json={"selected": [0]}).json()["questions"][0]["answer"]["is_correct"]

    register(client, "AnotherPaperUser")
    path = f"/api/exam-library/{paper['id']}"
    assert client.get(path).status_code == 404 and client.post(path + "/delete").status_code == 404
    assert client.get("/api/exam-library").json()["papers"] == []
    client.post("/api/auth/login", json={"username": "PaperUser", "password": PASSWORD})
    assert client.post(path + "/delete").status_code == 200
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(("filename", "format_name"), [("paper.pdf", "PDF"), ("paper.png", "PNG")])
def test_scans_and_photos_use_one_read_then_confirm(client, importer, filename, format_name):
    register(client, "PaperUser")
    stream = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(stream, format=format_name)
    assert read_files([(filename, stream.getvalue())])[0].images
    response = upload(client, filename, stream.getvalue())
    assert response.status_code == 201, response.text
    assert importer["prompts"] == [IMPORT_PROMPT]
    paper = response.json()["paper"]
    assert (paper["ready_count"], paper["draft_count"]) == (0, 2)
    first = paper["questions"][0]
    assert client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm").status_code == 200


def test_multicolumn_photo_single_read_and_targeted_retry(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    stream = io.BytesIO()
    image = Image.new("RGB", (1600, 2800), "white")
    draw = ImageDraw.Draw(image)
    draw.text((120, 220), "1. Find the quadratic coefficient.", fill="black")
    draw.text((920, 220), "2. Explain the axis of symmetry.", fill="black")
    draw.text((920, 1800), "3. [obscured formula]", fill="gray")
    image.save(stream, format="PNG")
    data = stream.getvalue()
    assert read_files([("two-columns.png", data)])[0].images

    state = {"correct_retry": False}

    def handler(prompt, content, _model):
        if prompt == IMPORT_PROMPT:
            return {"questions": [with_options(1, STEM), with_options(2, SECOND), with_options(3, "二次项系数是 2 还是 3？")],
                    "answers": [{"page": 1, "number": "1", "choices": ["A"], "evidence": "1. A"}]}
        assert prompt == RETRY_PROMPT
        number = "3" if state["correct_retry"] else "4"
        return {"questions": [with_options(number, "二次函数 y=2x² 的系数符号是什么？")],
                "answers": [{"page": 1, "number": number, "choices": ["A"], "evidence": f"{number}. A"}]}

    mock_upstream(handler)
    register(client, "PhotoUser")
    initial = upload(client, "two-columns.png", data)
    assert initial.status_code == 201, initial.text
    paper = initial.json()["paper"]
    assert (paper["question_count"], paper["draft_count"]) == (3, 3)
    assert [item["number"] for item in paper["questions"]] == ["1", "2", "3"]
    assert upload(client, "two-columns.png", data).json()["duplicate"]

    path = "/api/exam-library/" + paper["id"]
    files = [{"filename": "two-columns.png", "data": base64.b64encode(data).decode()}]
    result = client.post(path + "/reprocess", json={"consent": True, "files": files})
    assert result.status_code == 200, result.text
    assert [item["number"] for item in result.json()["paper"]["questions"]] == ["1", "2", "3"]

    pending = next(item for item in paper["questions"] if item["number"] == "3")
    retry = f"{path}/questions/{pending['id']}/retry"
    retry_files = [files[0] | {"filename": "question.png"}, files[0] | {"filename": "answer.png"}]
    assert client.post(retry, json={"consent": True, "files": retry_files}).status_code == 422
    state["correct_retry"] = True
    updated = client.post(retry, json={"consent": True, "files": retry_files})
    assert updated.status_code == 200, updated.text
    final = updated.json()["paper"]
    assert final["questions"][2]["id"] == pending["id"]
    assert final["questions"][2]["status"] == "draft"

    with database() as connection:
        account = connection.execute("SELECT account_id FROM imported_papers WHERE id = ?", (paper["id"],)).fetchone()
        rows = matching_questions(connection, account[0], "二次函数")
    assert rows == []


def test_same_number_in_different_sections_and_pages_is_not_merged():
    pages = [Page("paper.pdf", 1), Page("paper.pdf", 2)]
    reading = PaperReading.model_validate({
        "questions": [
            {"page": page, "number": number, "section": section, "stem": stem, "tags": ["二次函数"],
             "options": [{"label": label, "text": text} for label, text in zip("ABC", OPTIONS)]}
            for page, number, section, stem in [(1, "1", "A卷", STEM), (1, "1", "B卷", SECOND), (2, "1", None, STEM)]
        ],
        "answers": [{"page": 1, "number": "1", "choices": ["A"], "evidence": "1. A"}],
    })
    output = draft_questions(pages, [([1, 2], reading)])
    assert [(item["page"], item["section"], item["number"]) for item in output] == [
        (1, "A卷", "1"), (1, "B卷", "1"), (2, None, "1")]
    assert all(item["status"] == "draft" for item in output)


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
                                   "options": [{"label": label, "text": text} for label, text in zip("ABC", OPTIONS)]}],
                    "answers": [{"page": 1, "number": "1", "choices": ["A"], "evidence": "1. A"}]}
        if prompt == EXAM_SELECT_PROMPT:
            assert data["context"]["exam"] == expected["exam"]
            assert {item["stem"] for item in data["candidates"]} == ({chengdu} if expected["exam"] else {beijing, chengdu})
            index = next(i for i, item in enumerate(data["candidates"]) if item["stem"] == expected["stem"])
            return {"questions": [{"candidate": index, "topic": "二次函数", "correct": [0], "explanation": "系数为正。"}]}
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
        body = document("1. " + stem, *(f"{key}. {value}" for key, value in zip("ABC", OPTIONS)), "参考答案", "1. A")
        response = upload(client, "original.docx", body, exam=exam)
        assert response.status_code == 201
        paper = response.json()["paper"]
        confirmed = client.post(f"/api/exam-library/{paper['id']}/questions/{paper['questions'][0]['id']}/confirm")
        assert confirmed.status_code == 200, confirmed.text

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


def test_wrong_printed_question_number_cannot_be_used_for_grading(client, importer):
    register(client, "PaperUser")
    data = document("9. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)), "参考答案", "1. A")
    response = upload(client, "paper.docx", data)
    assert response.status_code == 201
    paper = response.json()["paper"]
    assert paper["ready_count"] == 0
    first = paper["questions"][0]
    confirmed = client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["paper"]["questions"][0]["status"] == "review_only"
    assert confirmed.json()["paper"]["ready_count"] == 0


def test_edit_resets_to_draft_and_confirm_restores(client, importer):
    register(client, "PaperUser")
    data = document("1. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)))
    paper = upload(client, "paper.docx", data).json()["paper"]
    first = paper["questions"][0]
    path = f"/api/exam-library/{paper['id']}/questions/{first['id']}"
    assert client.post(path + "/confirm").status_code == 200
    edited = client.patch(path, json={"stem": "修改后的题干", "options": ["甲", "乙", "丙"], "correct": [0]})
    assert edited.status_code == 200, edited.text
    question_after = edited.json()["paper"]["questions"][0]
    assert question_after["status"] == "draft" and question_after["stem"] == "修改后的题干"
    assert question_after["correct"] == [0]
    confirmed = client.post(path + "/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["paper"]["questions"][0]["status"] == "ready"


def test_confirm_validates_and_respects_ownership(client, importer):
    register(client, "PaperUser")
    data = document("1. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)))
    paper = upload(client, "paper.docx", data).json()["paper"]
    first = paper["questions"][0]
    path = f"/api/exam-library/{paper['id']}/questions/{first['id']}"
    assert client.patch(path, json={"stem": "", "options": [], "correct": []}).status_code == 422
    assert client.patch(path, json={"stem": "题干", "options": ["甲", "乙"], "correct": []}).status_code == 422
    assert client.patch(path, json={"stem": "题干", "options": ["甲", "乙", "丙"], "correct": [5]}).status_code == 422
    register(client, "OtherUser")
    assert client.post(path + "/confirm").status_code == 404
    assert client.patch(path, json={"stem": "题干", "options": ["甲", "乙", "丙"], "correct": [0]}).status_code == 404


def test_review_only_library_question_enters_practice(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    monkeypatch.setenv("EXAM_QUIZ_MODE", "debug")

    def handler(prompt, content, _model):
        if prompt == IMPORT_PROMPT:
            return {"questions": [with_options(1, STEM)], "answers": []}
        data = json.loads(content)
        if prompt == EXAM_SELECT_PROMPT:
            assert data["candidates"][0]["official_correct"] == []
            return {"questions": [{"candidate": 0, "topic": "二次函数", "correct": [0],
                                   "explanation": "二次项系数为正。"}]}
        if prompt == DRAFT_PROMPT:
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    mock_upstream(handler, goal_handler=lambda _data: {"verdict": "approved", "message": "通过", "exam": EXAM})
    register(client, "ReviewOnlyUser", "备考成都中考数学")
    body = document("1. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)))
    response = upload(client, "review-only.docx", body, exam="双流中学第一次模拟试题")
    assert response.status_code == 201, response.text
    paper = response.json()["paper"]
    assert (paper["draft_count"], paper["ready_count"]) == (1, 0)
    first = paper["questions"][0]
    assert client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm").status_code == 200

    headers = {"X-Study-Session": str(uuid4())}
    material = context(client) | {"version_id": str(uuid4())}
    created = client.post("/api/quizzes", headers=headers, json=material)
    quiz = client.get("/api/quizzes/" + created.json()["id"], headers=headers).json()
    assert quiz["status"] == "ready", quiz
    past = [item for item in quiz["questions"] if item["origin"] == "past"]
    assert past and past[0]["source"]["imported"] and past[0]["stem"] == STEM


def test_open_library_question_is_converted_to_choice(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    stem = "求二次函数 y=x^2-3x 的顶点横坐标。"

    def handler(prompt, content, _model):
        if prompt == IMPORT_PROMPT:
            return {"questions": [{"page": 1, "number": "1", "stem": stem, "tags": ["二次函数"]}], "answers": []}
        data = json.loads(content)
        if prompt == SELECT_OPEN_PROMPT:
            assert data["candidates"][0]["stem"] == stem
            return {"questions": [{"candidate": 0, "topic": "二次函数"}]}
        if prompt == CONVERT_TO_CHOICE_PROMPT:
            assert data["question"]["stem"] == stem
            return {"kind": "single", "topic": "二次函数", "stem": "二次函数 y=x^2-3x 的顶点横坐标是？",
                    "options": ["1.5", "-1.5", "0", "3"], "correct": [0], "explanation": "对称轴 x=-b/(2a)=1.5。"}
        if prompt == DRAFT_PROMPT:
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    mock_upstream(handler)
    register(client, "OpenQuestionUser", "学懂二次函数")
    response = upload(client, "open.docx", document("9. " + stem))
    assert response.status_code == 201, response.text
    paper = response.json()["paper"]
    first = paper["questions"][0]
    assert client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm").status_code == 200

    headers = {"X-Study-Session": str(uuid4())}
    material = context(client) | {"version_id": str(uuid4())}
    created = client.post("/api/quizzes", headers=headers, json=material)
    quiz = client.get("/api/quizzes/" + created.json()["id"], headers=headers).json()
    assert quiz["status"] == "ready", quiz
    past = [item for item in quiz["questions"] if item["origin"] == "past"]
    assert past and past[0]["kind"] == "single" and len(past[0]["options"]) >= 3
    assert past[0]["stem"] == "二次函数 y=x^2-3x 的顶点横坐标是？"
    assert past[0]["source"]["imported"]


def test_import_merges_same_exam_papers(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")

    def handler(prompt, content, _model):
        assert prompt == IMPORT_PROMPT
        text = content[0]["text"] if isinstance(content, list) else content
        stem = "甲题" if "甲题" in text else "乙题"
        return {"questions": [{"page": 1, "number": "1", "stem": stem, "tags": ["二次函数"],
                               "options": [{"label": key, "text": value} for key, value in zip("ABC", OPTIONS)]}],
                "answers": [{"page": 1, "number": "1", "choices": ["A"], "evidence": "1. A"}]}

    mock_upstream(handler)
    register(client, "MergeUser")
    first = upload(client, "a.docx", document("1. 甲题", "A. 甲", "B. 乙", "C. 丙"),
                   exam="双流中学第一次模拟试题")
    assert first.status_code == 201, first.text
    second = upload(client, "b.docx", document("1. 乙题", "A. 甲", "B. 乙", "C. 丙"),
                    exam="双流中学第一次模拟试题")
    assert second.status_code == 201, second.text
    assert second.json()["merged"] is True
    papers = client.get("/api/exam-library").json()["papers"]
    assert len(papers) == 1
    assert papers[0]["question_count"] == 2
    assert set(papers[0]["filenames"]) == {"a.docx", "b.docx"}


def test_merge_duplicate_papers_migrates_existing(client):
    register(client, "MigrateUser")
    with database() as connection:
        account = connection.execute("SELECT id FROM users WHERE username = ?", ("MigrateUser",)).fetchone()["id"]
        connection.execute("BEGIN IMMEDIATE")
        for index, paper_id in enumerate(("paper-a", "paper-b"), 1):
            connection.execute(
                """INSERT INTO imported_papers (id, account_id, exam, exam_key, subject, subject_key, filenames, fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (paper_id, account, "双流中学第一次模拟试题", store.exam_key("双流中学第一次模拟试题", "数学"),
                 "数学", store.compact("数学"), json.dumps([f"{paper_id}.png"]), f"fingerprint-{index}"))
            item = {"number": str(index), "file": f"{paper_id}.png", "page": 1, "section": None, "section_order": 0,
                    "stem": f"第 {index} 题", "options": [], "correct": [], "tags": ["二次函数"], "kind": "other",
                    "ready": False, "confirmed": True, "status": "review_only", "reason": ""}
            connection.execute(
                "INSERT INTO imported_questions (data, searchable, ready, confirmed, paper_id) VALUES (?, ?, ?, ?, ?)",
                (json.dumps(item, ensure_ascii=False), "题", 0, 1, paper_id))
        store.merge_duplicate_papers(connection)
    with database() as connection:
        papers = store.list_papers(connection, account)
    assert len(papers) == 1
    assert papers[0]["question_count"] == 2
    assert set(papers[0]["filenames"]) == {"paper-a.png", "paper-b.png"}


def test_all_candidates_are_sent_to_api(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    quadratic = "已知二次函数 y=ax^2+bx+c 的图象开口向上。"
    inverse = "反比例函数 y=1/x 的图象位于哪些象限？"
    seen = {"stems": []}

    def handler(prompt, content, _model):
        if prompt == IMPORT_PROMPT:
            return {"questions": [
                {"page": 1, "number": "1", "stem": quadratic, "tags": ["二次函数"],
                 "options": [{"label": key, "text": value} for key, value in zip("ABC", OPTIONS)]},
                {"page": 1, "number": "2", "stem": inverse, "tags": ["反比例函数"],
                 "options": [{"label": key, "text": value} for key, value in zip("ABC", OPTIONS)]},
            ], "answers": []}
        data = json.loads(content)
        if prompt == EXAM_SELECT_PROMPT:
            seen["stems"] = [item["stem"] for item in data["candidates"]]
            index = seen["stems"].index(quadratic)
            return {"questions": [{"candidate": index, "topic": "二次函数", "correct": [0],
                                   "explanation": "二次项系数为正。"}]}
        if prompt == DRAFT_PROMPT:
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    mock_upstream(handler)
    register(client, "AllCandidateUser", "备考成都中考数学")
    body = document("1. " + quadratic, "2. " + inverse)
    response = upload(client, "two.docx", body)
    assert response.status_code == 201, response.text
    paper = response.json()["paper"]
    for item in paper["questions"]:
        assert client.post(f"/api/exam-library/{paper['id']}/questions/{item['id']}/confirm").status_code == 200

    headers = {"X-Study-Session": str(uuid4())}
    material = context(client) | {"version_id": str(uuid4())}
    created = client.post("/api/quizzes", headers=headers, json=material)
    quiz = client.get("/api/quizzes/" + created.json()["id"], headers=headers).json()
    assert quiz["status"] == "ready", quiz
    assert quadratic in seen["stems"] and inverse in seen["stems"]
    past = [item for item in quiz["questions"] if item["origin"] == "past"]
    assert past and past[0]["stem"] == quadratic


def test_open_question_rejected_by_api_is_not_converted(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")

    def unavailable(*_args, **_kwargs):
        raise ExamUnavailable("无真题")

    monkeypatch.setattr("backend.quizzes.find_exam_questions", unavailable)
    stem = "反比例函数 y=1/x 的图象位于哪些象限？"
    state = {"converted": False}

    def handler(prompt, content, _model):
        if prompt == IMPORT_PROMPT:
            return {"questions": [{"page": 1, "number": "1", "stem": stem, "tags": ["反比例函数"]}], "answers": []}
        data = json.loads(content)
        if prompt == SELECT_OPEN_PROMPT:
            assert data["candidates"][0]["stem"] == stem
            return {"questions": []}
        if prompt == CONVERT_TO_CHOICE_PROMPT:
            state["converted"] = True
            return {"kind": "single", "topic": "反比例函数", "stem": "改写题",
                    "options": ["甲", "乙", "丙"], "correct": [0], "explanation": "解析"}
        if prompt == DRAFT_PROMPT:
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "single"),
                                                          question(401, "二次函数", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    mock_upstream(handler)
    register(client, "RejectOpenUser", "学懂二次函数")
    response = upload(client, "inverse.docx", document("1. " + stem))
    paper = response.json()["paper"]
    first = paper["questions"][0]
    assert client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm").status_code == 200

    headers = {"X-Study-Session": str(uuid4())}
    material = context(client) | {"version_id": str(uuid4())}
    created = client.post("/api/quizzes", headers=headers, json=material)
    quiz = client.get("/api/quizzes/" + created.json()["id"], headers=headers).json()
    assert quiz["status"] == "ready", quiz
    assert not [item for item in quiz["questions"] if item["origin"] == "past"]
    assert state["converted"] is False


def test_edit_tags_keeps_status_and_updates_search(client, importer):
    register(client, "TagUserEdit")
    data = document("1. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)), "参考答案", "1. A")
    paper = upload(client, "tags.docx", data).json()["paper"]
    first = paper["questions"][0]
    assert client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm").status_code == 200
    path = f"/api/exam-library/{paper['id']}/questions/{first['id']}/tags"
    updated = client.patch(path, json={"tags": ["二次函数", "新知识点"]})
    assert updated.status_code == 200, updated.text
    question = updated.json()["paper"]["questions"][0]
    assert question["tags"] == ["二次函数", "新知识点"]
    assert question["status"] == "ready" and question["confirmed"] is True
    with database() as connection:
        account = connection.execute("SELECT account_id FROM imported_papers WHERE id = ?", (paper["id"],)).fetchone()
        rows = matching_questions(connection, account[0], "新知识点")
    assert len(rows) == 1


def test_tags_validation_and_ownership(client, importer):
    register(client, "TagUserValidate")
    data = document("1. " + STEM, *(f"{label}. {text}" for label, text in zip("ABC", OPTIONS)))
    paper = upload(client, "tags.docx", data).json()["paper"]
    first = paper["questions"][0]
    path = f"/api/exam-library/{paper['id']}/questions/{first['id']}/tags"
    assert client.patch(path, json={"tags": []}).status_code == 422
    assert client.patch(path, json={"tags": [f"标签{i}" for i in range(9)]}).status_code == 422
    assert client.patch(path, json={"tags": ["  "]}).status_code == 422
    register(client, "OtherTagUser")
    assert client.patch(path, json={"tags": ["二次函数"]}).status_code == 404


def test_convert_to_choice_retries_with_review_feedback():
    state = {"generate": 0, "review": 0, "feedback": []}

    def handler(request):
        payload = json.loads(request.content)
        prompt = payload["messages"][0]["content"]
        content = payload["messages"][1]["content"]
        if prompt == CONVERT_TO_CHOICE_PROMPT:
            state["generate"] += 1
            state["feedback"].append(json.loads(content).get("feedback"))
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
                "kind": "single", "topic": "二次函数", "stem": f"改写 {state['generate']}",
                "options": ["甲", "乙", "丙"], "correct": [0], "explanation": "解析"})}}]})
        assert prompt == FIRST_REVIEW_PROMPT
        state["review"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "answers": [[1]] if state["review"] == 1 else [[0]], "issues": []})}}]})

    async def run():
        settings = ModelSettings("https://model.example/v1", "test", "flash")
        context = SimpleNamespace(question="二次函数", lesson=SimpleNamespace(title="二次函数", summary="二次函数的性质"))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await convert_to_choice({"stem": "原题", "tags": ["二次函数"]}, context, client, settings=settings)

    question = asyncio.run(run())
    assert state["generate"] == 2 and state["review"] == 2
    assert state["feedback"][0] == []
    assert any("初审独立求解为 B" in item for item in state["feedback"][1])
    assert question.stem == "改写 2" and question.correct == [0]


def test_quiz_allows_single_simulated_with_past(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")
    monkeypatch.setenv("EXAM_QUIZ_MODE", "debug")

    def handler(prompt, content, _model):
        if prompt == IMPORT_PROMPT:
            return {"questions": [with_options(1, STEM)], "answers": []}
        data = json.loads(content)
        if prompt == EXAM_SELECT_PROMPT:
            return {"questions": [{"candidate": 0, "topic": "二次函数", "correct": [0], "explanation": "开口向上。"}]}
        if prompt == DRAFT_PROMPT:
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "single")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": []}

    mock_upstream(handler)
    register(client, "SinglePastUser", "学懂二次函数")
    response = upload(client, "single.docx", document("1. " + STEM, "A. 大于零", "B. 小于零", "C. 等于零"))
    paper = response.json()["paper"]
    first = paper["questions"][0]
    assert client.post(f"/api/exam-library/{paper['id']}/questions/{first['id']}/confirm").status_code == 200

    headers = {"X-Study-Session": str(uuid4())}
    material = context(client) | {"version_id": str(uuid4())}
    created = client.post("/api/quizzes", headers=headers, json=material)
    quiz = client.get("/api/quizzes/" + created.json()["id"], headers=headers).json()
    assert quiz["status"] == "ready", quiz
    past = [item for item in quiz["questions"] if item["origin"] == "past"]
    simulated = [item for item in quiz["questions"] if item["origin"] == "simulated"]
    assert past and past[0]["stem"] == STEM
    assert simulated and simulated[0]["kind"] == "single"


def test_quiz_fails_after_ten_review_failures(client, monkeypatch):
    monkeypatch.setenv("EXAM_DEEPSEEK_API_KEY", "exam-test")

    def unavailable(*_args, **_kwargs):
        raise ExamUnavailable("无真题")

    monkeypatch.setattr("backend.quizzes.find_exam_questions", unavailable)

    def handler(prompt, content, _model):
        data = json.loads(content) if isinstance(content, str) and content.startswith("{") else content
        if prompt == DRAFT_PROMPT:
            return {"topics": ["二次函数"], "questions": [question(400, "二次函数", "single"),
                                                          question(401, "二次函数", "multiple")]}
        assert prompt == FIRST_REVIEW_PROMPT
        return {"answers": [item["correct"] for item in data["draft"]["questions"]], "issues": ["核对题干"]}

    mock_upstream(handler)
    register(client, "RetryFailUser", "学懂二次函数")
    headers = {"X-Study-Session": str(uuid4())}
    material = context(client) | {"version_id": str(uuid4())}
    created = client.post("/api/quizzes", headers=headers, json=material)
    quiz = client.get("/api/quizzes/" + created.json()["id"], headers=headers).json()
    assert quiz["status"] == "failed"
    assert "未通过初审" in quiz["message"]
