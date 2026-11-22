"""
Tests for the customer support tools, NLP entity extraction and escalation rule.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models import ChatSession, MessageAnalysis, Order, OrderItem, Product, ReturnRequest, SupportTicket
from app.support import nlp
from app.support.engine import escalation_reason, record_user_turn
from app.support.tools import (ToolContext, cancel_order, create_return_request, escalate_to_human,
                               get_order_status, priority_for, search_products)


@pytest.fixture
def catalog(db_session):
    products = [
        Product(sku="ELE-001", name="SoundWave Pro Wireless Headphones", category="Electronics", price=3499, stock=5),
        Product(sku="ELE-006", name="ArmorShield Phone Case", category="Accessories", price=499, stock=0),
    ]
    db_session.add_all(products)
    db_session.commit()
    return products


def make_order(db, user, number, status, products, delivered_days_ago=None):
    now = datetime.now(timezone.utc)
    order = Order(order_number=number, user_id=user.id, status=status, total=sum(p.price for p in products),
                  delivered_at=now - timedelta(days=delivered_days_ago) if delivered_days_ago is not None else None)
    order.items = [OrderItem(product_id=p.id, quantity=1, unit_price=p.price) for p in products]
    db.add(order)
    db.commit()
    return order


@pytest.mark.unit
@pytest.mark.parametrize("text,expected", [
    ("Where is ORD-10023?", "ORD-10023"),
    ("order number 10021 is late", "ORD-10021"),
    ("track ord 10025 please", "ORD-10025"),
    ("my order #10024", "ORD-10024"),
    ("I paid 3499 rupees", None),
])
def test_order_number_extraction(text, expected):
    assert nlp.extract_entities_regex(text).get("order_number") == expected


@pytest.mark.unit
def test_regex_entities_email_phone_amount():
    entities = nlp.extract_entities_regex("Mail me at a.b@example.com or call 9876543210, I paid ₹1,299")
    assert entities["email"] == "a.b@example.com"
    assert entities["phone"] == "9876543210"
    assert entities["amount"] == "1,299"


@pytest.mark.unit
def test_lexicon_sentiment():
    assert nlp.lexicon_sentiment("This is the worst, terrible service!!")[0] == "negative"
    assert nlp.lexicon_sentiment("thanks, that was great")[0] == "positive"
    assert nlp.lexicon_sentiment("where is my order")[0] == "neutral"


@pytest.mark.unit
def test_analyze_falls_back_to_baseline_when_llm_fails():
    with patch("app.support.nlp._llm_analyze", side_effect=RuntimeError("no api")):
        result = nlp.analyze("I want to cancel my order ORD-10024")
    assert result.classifier == "baseline"
    assert result.intent == "cancel_order"
    assert result.entities["order_number"] == "ORD-10024"


@pytest.mark.integration
def test_order_lookup_is_scoped_to_customer(db_session, test_user, second_test_user, catalog):
    make_order(db_session, second_test_user, "ORD-20001", "shipped", catalog[:1])
    ctx = ToolContext(db=db_session, user_id=test_user.id)
    assert get_order_status(ctx, "ORD-20001")["found"] is False
    other_ctx = ToolContext(db=db_session, user_id=second_test_user.id)
    assert get_order_status(other_ctx, "order 20001")["status"] == "shipped"


@pytest.mark.integration
def test_return_within_window_creates_request(db_session, test_user, catalog):
    make_order(db_session, test_user, "ORD-10021", "delivered", catalog, delivered_days_ago=5)
    ctx = ToolContext(db=db_session, user_id=test_user.id)
    result = create_return_request(ctx, "ORD-10021", reason="broken", product="headphones")
    assert result["success"] is True
    assert result["product"] == "SoundWave Pro Wireless Headphones"
    assert db_session.query(ReturnRequest).count() == 1
    # A second request for the same item is rejected
    assert create_return_request(ctx, "ORD-10021", reason="broken", product="headphones")["success"] is False


@pytest.mark.integration
def test_return_outside_window_rejected(db_session, test_user, catalog):
    make_order(db_session, test_user, "ORD-10022", "delivered", catalog[:1], delivered_days_ago=45)
    result = create_return_request(ToolContext(db=db_session, user_id=test_user.id), "ORD-10022", reason="no longer needed")
    assert result["success"] is False
    assert "return window" in result["message"]


@pytest.mark.integration
def test_return_asks_which_item_when_ambiguous(db_session, test_user, catalog):
    make_order(db_session, test_user, "ORD-10028", "delivered", catalog, delivered_days_ago=2)
    result = create_return_request(ToolContext(db=db_session, user_id=test_user.id), "ORD-10028", reason="defective")
    assert result.get("needs_clarification") is True
    assert len(result["items"]) == 2


@pytest.mark.integration
def test_return_requires_delivered_order(db_session, test_user, catalog):
    make_order(db_session, test_user, "ORD-10023", "shipped", catalog[:1])
    result = create_return_request(ToolContext(db=db_session, user_id=test_user.id), "ORD-10023", reason="changed mind")
    assert result["success"] is False


@pytest.mark.integration
def test_cancel_only_before_shipping(db_session, test_user, catalog):
    ctx = ToolContext(db=db_session, user_id=test_user.id)
    placed = make_order(db_session, test_user, "ORD-10024", "placed", catalog[:1])
    make_order(db_session, test_user, "ORD-10025", "shipped", catalog[:1])
    assert cancel_order(ctx, "ORD-10024")["success"] is True
    assert placed.status == "cancelled"
    assert cancel_order(ctx, "ORD-10025")["success"] is False


@pytest.mark.integration
def test_search_products(db_session, test_user, catalog):
    products = search_products(ToolContext(db=db_session, user_id=test_user.id), "headphones")["products"]
    assert products[0]["sku"] == "ELE-001"
    assert products[0]["in_stock"] is True


@pytest.mark.unit
@pytest.mark.parametrize("score,priority", [(-0.9, "urgent"), (-0.6, "high"), (-0.2, "normal"), (0.5, "low"), (None, "normal")])
def test_priority_from_sentiment(score, priority):
    assert priority_for(score) == priority


@pytest.mark.integration
def test_escalation_reuses_open_ticket(db_session, test_user):
    session = ChatSession(owner_id=test_user.id, title="t", channel="text")
    db_session.add(session)
    db_session.commit()
    ctx = ToolContext(db=db_session, user_id=test_user.id, session_id=session.id, sentiment_score=-0.9)
    first = escalate_to_human(ctx, reason="angry")
    second = escalate_to_human(ctx, reason="still angry")
    assert first["priority"] == "urgent"
    assert second["ticket_id"] == first["ticket_id"]
    assert db_session.query(SupportTicket).count() == 1


@pytest.mark.integration
def test_record_user_turn_escalates_on_negative_sentiment(db_session, test_user):
    session = ChatSession(owner_id=test_user.id, title="t", channel="voice")
    db_session.add(session)
    db_session.commit()
    angry = nlp.Analysis(intent="complaint", confidence=0.9, sentiment_label="negative", sentiment_score=-0.85)
    with patch("app.support.engine.nlp.analyze", return_value=angry):
        row, analysis, ticket = record_user_turn(db_session, session, test_user.id, "This is a scam!!")
    assert row.escalated is True
    assert row.channel == "voice"
    assert ticket["priority"] == "urgent"


@pytest.mark.integration
def test_escalation_after_three_out_of_scope_turns(db_session, test_user):
    session = ChatSession(owner_id=test_user.id, title="t", channel="text")
    db_session.add(session)
    db_session.commit()
    other = nlp.Analysis(intent="other", confidence=0.9)
    assert escalation_reason(db_session, session.id, other) is None
    for i in range(2):
        db_session.add(MessageAnalysis(message_id=i + 1, session_id=session.id, channel="text", intent="other", escalated=False))
    db_session.commit()
    assert "3 attempts" in escalation_reason(db_session, session.id, other)
