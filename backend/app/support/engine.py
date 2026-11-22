"""
Customer support engine: runs one conversation turn.

Pipeline per user message:
  1. NLP analysis (intent, entities, sentiment)      -> nlp.analyze
  2. Escalation rule (negative sentiment / asks for a human / repeated out-of-scope turns)
  3. LLM with tool calling over the customer's data  -> tools.py
  4. Persist messages + MessageAnalysis (with response time) for the evaluation metrics

record_user_turn() is shared with the LiveKit voice agent, which runs its own LLM loop.
"""
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ChatMessage, ChatSession, MessageAnalysis
from app.services.document_service import get_openai_client
from app.support import nlp
from app.support.tools import TOOL_SPECS, ToolContext, escalate_to_human, run_tool

logger = logging.getLogger(__name__)

STORE_NAME = "ShopEase"
HISTORY_LIMIT = 10
MAX_TOOL_ROUNDS = 5

SUPPORT_PROMPT = f"""You are the customer support assistant for {STORE_NAME}, an online store in India.
You help customers with FAQs and policies, order tracking, returns and refunds, cancellations and product questions.

Rules:
- Always use the tools to look up orders, products and policies. Never invent order details, dates, prices or policies.
- If the customer hasn't given an order number, ask for it or offer to list their recent orders.
- Confirm the item and reason before creating a return. Confirm before cancelling an order.
- If a tool says something isn't possible, explain why and offer the next best option.
- If the customer asks for a human, is very upset, or you cannot resolve the issue, use escalate_to_human.
- Be warm, concise and professional. Apologise sincerely when something went wrong.
- Prices are in Indian rupees (₹)."""

TEXT_STYLE = "\nFormat answers for a chat window: short paragraphs, **bold** key facts, bullet lists where helpful."
VOICE_STYLE = ("\nYou are speaking on a phone call. Reply in one to three short spoken sentences. "
               "No markdown, lists or emojis. Read order numbers as 'O R D' followed by the digits.")


class SupportError(Exception):
    pass


def create_support_session(db: Session, user_id: int, channel: str) -> ChatSession:
    session = ChatSession(owner_id=user_id, channel=channel,
                          title=f"Support {channel} {datetime.now().strftime('%d %b %H:%M')}")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_support_session(db: Session, session_id: int, user_id: int) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.owner_id == user_id,
                                           ChatSession.channel.isnot(None)).first()
    if not session:
        raise SupportError("Support session not found")
    return session


def get_history(db: Session, session_id: int, limit: int = HISTORY_LIMIT) -> List[Dict]:
    rows = (db.query(ChatMessage).filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.desc()).limit(limit).all())
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def escalation_reason(db: Session, session_id: int, analysis: nlp.Analysis) -> Optional[str]:
    """Decide whether this turn must be escalated to a human, and why."""
    if analysis.intent == "talk_to_human":
        return "Customer asked for a human agent"
    if analysis.sentiment_score <= settings.ESCALATION_SENTIMENT_THRESHOLD:
        return f"Strong negative sentiment ({analysis.sentiment_score:+.2f})"
    if analysis.intent == "other":
        previous = (db.query(MessageAnalysis.intent).filter(MessageAnalysis.session_id == session_id)
                    .order_by(MessageAnalysis.id.desc()).limit(2).all())
        if len(previous) == 2 and all(p.intent == "other" for p in previous):
            return "Bot could not understand the request after 3 attempts"
    return None


def record_user_turn(db: Session, session: ChatSession, user_id: int, message: str,
                     history: Optional[List[Dict]] = None) -> Tuple[MessageAnalysis, nlp.Analysis, Optional[Dict]]:
    """
    Analyze and persist a user message, applying the escalation rule.

    Returns (analysis_row, analysis, ticket) where ticket is the escalate_to_human result or None.
    The caller commits and fills analysis_row.response_time_ms once the reply is ready.
    """
    analysis = nlp.analyze(message, history)

    user_msg = ChatMessage(session_id=session.id, role="user", content=message)
    db.add(user_msg)
    db.flush()

    ticket = None
    reason = escalation_reason(db, session.id, analysis)
    if reason:
        ctx = ToolContext(db=db, user_id=user_id, session_id=session.id, channel=session.channel,
                          sentiment_score=analysis.sentiment_score)
        ticket = escalate_to_human(ctx, reason=reason, summary=message)
        logger.info(f"Session {session.id} escalated: {reason} -> ticket #{ticket['ticket_id']}")

    row = MessageAnalysis(
        message_id=user_msg.id, session_id=session.id, channel=session.channel,
        intent=analysis.intent, intent_confidence=analysis.confidence, classifier=analysis.classifier,
        entities=analysis.entities, sentiment_label=analysis.sentiment_label,
        sentiment_score=analysis.sentiment_score, escalated=ticket is not None,
    )
    db.add(row)
    db.flush()
    return row, analysis, ticket


def analysis_note(analysis: nlp.Analysis, ticket: Optional[Dict]) -> str:
    note = (f"NLP analysis of the latest customer message: intent={analysis.intent}, "
            f"entities={json.dumps(analysis.entities)}, sentiment={analysis.sentiment_label} ({analysis.sentiment_score:+.2f}).")
    if ticket:
        note += (f" This conversation has been escalated to a human: {ticket['message']} "
                 "Tell the customer this, apologise if they are upset, and still help with anything you can.")
    return note


def _run_llm(ctx: ToolContext, history: List[Dict], message: str, note: str) -> str:
    client = get_openai_client()
    if client is None:
        raise SupportError("OpenAI client not initialized. Please configure OPENAI_API_KEY.")

    messages: List[Dict] = [{"role": "system", "content": SUPPORT_PROMPT + TEXT_STYLE + "\n\n" + note}]
    messages += history
    messages.append({"role": "user", "content": message})

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=settings.SUPPORT_MODEL, messages=messages, tools=TOOL_SPECS, temperature=0.3, max_tokens=600)
        choice = response.choices[0].message
        if not choice.tool_calls:
            return (choice.content or "").strip()

        messages.append({"role": "assistant", "content": choice.content or "",
                         "tool_calls": [tc.model_dump() for tc in choice.tool_calls]})
        for tc in choice.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(ctx, tc.function.name, args)
            logger.info(f"Tool {tc.function.name}({args}) -> {str(result)[:200]}")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})

    return "Sorry, I'm having trouble completing that right now. Let me connect you with a human agent."


def handle_turn(db: Session, session_id: int, user_id: int, message: str) -> Dict:
    """Process one text-chat turn end to end and return the reply with its analysis."""
    start = time.perf_counter()
    session = get_support_session(db, session_id, user_id)
    history = get_history(db, session.id)

    try:
        row, analysis, ticket = record_user_turn(db, session, user_id, message, history)
        ctx = ToolContext(db=db, user_id=user_id, session_id=session.id, channel=session.channel,
                          sentiment_score=analysis.sentiment_score)
        answer = _run_llm(ctx, history, message, analysis_note(analysis, ticket))

        db.add(ChatMessage(session_id=session.id, role="assistant", content=answer))
        row.response_time_ms = round((time.perf_counter() - start) * 1000, 1)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "session_id": session.id,
        "answer": answer,
        "intent": analysis.intent,
        "intent_confidence": analysis.confidence,
        "classifier": analysis.classifier,
        "entities": analysis.entities,
        "sentiment_label": analysis.sentiment_label,
        "sentiment_score": analysis.sentiment_score,
        "escalated": ticket is not None,
        "ticket_id": ticket["ticket_id"] if ticket else None,
        "response_time_ms": row.response_time_ms,
    }
