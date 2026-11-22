"""
Tests for the support router and the LiveKit token endpoint.
"""
import json
from unittest.mock import patch

import pytest
from jose import jwt

from app.config import settings
from app.models import ChatSession, Feedback, MessageAnalysis
from app.support import nlp


@pytest.fixture
def no_openai():
    """Run the engine without network calls: fixed analysis and a canned LLM reply."""
    analysis = nlp.Analysis(intent="order_status", confidence=0.95, entities={"order_number": "ORD-10023"})
    with patch("app.support.engine.nlp.analyze", return_value=analysis), \
         patch("app.support.engine._run_llm", return_value="Your order **ORD-10023** has shipped."):
        yield


@pytest.mark.integration
def test_support_chat_creates_session_and_logs_analysis(authenticated_client, db_session, no_openai):
    response = authenticated_client.post("/support/chat", json={"message": "Where is ORD-10023?"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "order_status"
    assert data["entities"]["order_number"] == "ORD-10023"
    assert data["escalated"] is False
    assert data["response_time_ms"] is not None

    session = db_session.get(ChatSession, data["session_id"])
    assert session.channel == "text"
    assert db_session.query(MessageAnalysis).count() == 1

    history = authenticated_client.get(f"/support/sessions/{data['session_id']}").json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
    assert history["messages"][0]["intent"] == "order_status"


@pytest.mark.integration
def test_support_chat_rejects_other_users_session(client, db_session, second_test_user, auth_headers, no_openai):
    session = ChatSession(owner_id=second_test_user.id, title="theirs", channel="text")
    db_session.add(session)
    db_session.commit()
    response = client.post("/support/chat", json={"session_id": session.id, "message": "hi"}, headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.integration
def test_feedback_and_metrics(authenticated_client, db_session, no_openai):
    chat = authenticated_client.post("/support/chat", json={"message": "Where is ORD-10023?"}).json()
    response = authenticated_client.post("/support/feedback", json={
        "session_id": chat["session_id"], "channel": "text", "rating": 4, "resolved": True, "comment": "quick"})
    assert response.status_code == 201
    assert db_session.query(Feedback).count() == 1

    metrics = authenticated_client.get("/support/metrics").json()
    assert metrics["satisfaction"]["text"]["average_rating"] == 4
    assert metrics["satisfaction"]["all"]["resolved_pct"] == 100.0
    assert metrics["response_time"]["text"]["count"] == 1
    assert metrics["intent_distribution"] == {"order_status": 1}


@pytest.mark.integration
def test_feedback_rating_validated(authenticated_client):
    assert authenticated_client.post("/support/feedback", json={"rating": 6}).status_code == 422


@pytest.mark.integration
def test_livekit_token_requires_configuration(authenticated_client):
    with patch.object(settings, "LIVEKIT_URL", ""):
        response = authenticated_client.post("/voice/livekit-token")
    assert response.status_code == 503


@pytest.mark.integration
def test_livekit_token_dispatches_support_agent(authenticated_client, db_session, test_user):
    with patch.object(settings, "LIVEKIT_URL", "wss://example.livekit.cloud"), \
         patch.object(settings, "LIVEKIT_API_KEY", "APIkey123"), \
         patch.object(settings, "LIVEKIT_API_SECRET", "s" * 40):
        response = authenticated_client.post("/voice/livekit-token")
    assert response.status_code == 200
    data = response.json()
    assert data["server_url"] == "wss://example.livekit.cloud"

    claims = jwt.decode(data["token"], "s" * 40, algorithms=["HS256"], options={"verify_aud": False})
    assert claims["sub"] == f"user-{test_user.id}"
    assert claims["video"]["room"] == data["room"]
    assert claims["roomConfig"]["agents"][0]["agentName"] == settings.LIVEKIT_AGENT_NAME
    meta = json.loads(claims["metadata"])
    assert meta == {"user_id": test_user.id, "session_id": data["session_id"], "name": test_user.name}
    assert db_session.get(ChatSession, data["session_id"]).channel == "voice"
