import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app, model_client
from backend.model import MAX_RESPONSE_BYTES

URL = "/api/lessons/generate"
CONFIG_KEYS = ("MODEL_BASE_URL", "MODEL_API_KEY", "MODEL_NAME")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def set_upstream(monkeypatch):
    monkeypatch.setenv("MODEL_BASE_URL", "https://model.example/v1/")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")

    def register(respond):
        async def mocked_client():
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                yield client
        app.dependency_overrides[model_client] = mocked_client

    return register


@pytest.mark.parametrize("result", [
    {"kind": "lesson", "title": "测试课程", "summary": "点击按钮", "html": "<button>点击</button>",
     "css": "", "javascript": "document.querySelector('button').disabled = false"},
    {"kind": "clarification", "message": "请提供函数表达式。"},
    {"kind": "out_of_scope", "message": "仅支持数学与计算机问题。"},
])
def test_live_contract(client, set_upstream, result):
    def upstream(request):
        assert str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["messages"][-1] == {"role": "user", "content": "给我解释递归"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    set_upstream(upstream)
    response = client.post(URL, json={"question": " 给我解释递归 "})
    assert response.status_code == 200
    assert response.json() == {"source": "live", "result": result}


@pytest.mark.parametrize("content", [
    "invalid JSON",
    '{"kind":"lesson","title":"缺字段"}',
    json.dumps({"kind": "clarification", "message": "a" * 501}),
])
def test_invalid_model_result(client, set_upstream, content):
    set_upstream(lambda _: httpx.Response(200, json={"choices": [{"message": {"content": content}}]}))
    response = client.post(URL, json={"question": "测试问题"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_model_response"


def test_oversized_upstream_response(client, set_upstream):
    set_upstream(lambda _: httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1)))
    response = client.post(URL, json={"question": "测试问题"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_model_response"


def test_timeout(client, set_upstream):
    def upstream(request):
        raise httpx.ReadTimeout("timeout", request=request)

    set_upstream(upstream)
    response = client.post(URL, json={"question": "测试问题"})
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "model_timeout"


def test_upstream_error_hides_provider_body(client, set_upstream):
    set_upstream(lambda _: httpx.Response(401, text="internal provider details"))
    response = client.post(URL, json={"question": "测试问题"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "model_unavailable"
    assert "internal provider details" not in response.text


@pytest.mark.parametrize("example_id", ["quadratic", "recursion"])
def test_example_without_config(client, monkeypatch, example_id):
    for key in CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)
    response = client.get(f"/api/examples/{example_id}")
    assert response.status_code == 200
    assert response.json()["source"] == "example"
    assert response.json()["result"]["kind"] == "lesson"


def test_missing_config_and_invalid_question(client, monkeypatch):
    for key in CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)
    response = client.post(URL, json={"question": "测试问题"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_not_configured"
    assert client.post(URL, json={"question": "   "}).status_code == 422
    assert client.post(URL, json={"question": "a" * 2001}).status_code == 422
    assert client.get("/api/examples/unknown").status_code == 404


def test_revision_sends_original_question_instruction_and_selected_version(client, set_upstream):
    lesson = client.get("/api/examples/recursion").json()["result"]
    updated = {**lesson, "title": "可暂停的递归演示"}

    def upstream(request):
        payload = json.loads(request.content)
        assert "待修改的数据" in payload["messages"][0]["content"]
        assert json.loads(payload["messages"][1]["content"]) == {
            "question": "讲解递归",
            "instruction": "增加暂停按钮",
            "lesson": lesson,
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(updated)}}]})

    set_upstream(upstream)
    response = client.post("/api/lessons/revise", json={
        "question": "讲解递归", "instruction": " 增加暂停按钮 ", "lesson": lesson,
    })
    assert response.status_code == 200
    assert response.json() == {"source": "live", "result": updated}
    assert client.post("/api/lessons/revise", json={
        "question": "讲解递归", "instruction": "  ", "lesson": lesson,
    }).status_code == 422
