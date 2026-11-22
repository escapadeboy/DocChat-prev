"""
Customer support router: text chat, orders, feedback, escalation tickets and evaluation metrics.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ChatMessage, ChatSession, Feedback, MessageAnalysis, Order, SupportTicket, User
from app.support.engine import SupportError, create_support_session, get_support_session, handle_turn
from app.support.metrics import compute_metrics
from app.support.tools import ToolContext, list_recent_orders

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])
limiter = Limiter(key_func=get_remote_address)

PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


class SupportChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=2000)


class FeedbackRequest(BaseModel):
    session_id: Optional[int] = None
    channel: str = Field("text", pattern="^(text|voice)$")
    rating: int = Field(..., ge=1, le=5)
    resolved: Optional[bool] = None
    comment: Optional[str] = Field(None, max_length=2000)


class TicketUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|assigned|resolved)$")


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Start a new text support conversation."""
    session = create_support_session(db, current_user.id, "text")
    return {"session_id": session.id, "title": session.title}


@router.get("/sessions/{session_id}")
async def get_session(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get a support conversation with the analysis of each user turn."""
    try:
        session = get_support_session(db, session_id, current_user.id)
    except SupportError as e:
        raise HTTPException(status_code=404, detail=str(e))
    analyses = {a.message_id: a for a in db.query(MessageAnalysis).filter(MessageAnalysis.session_id == session.id)}
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.id).all()
    return {"session_id": session.id, "channel": session.channel, "title": session.title, "messages": [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at,
         "intent": analyses[m.id].intent if m.id in analyses else None,
         "sentiment_label": analyses[m.id].sentiment_label if m.id in analyses else None}
        for m in messages]}


@router.post("/chat")
@limiter.limit("30/minute")
async def support_chat(request: Request, body: SupportChatRequest,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Send a message to the support bot. Creates a session if none is given."""
    session_id = body.session_id or create_support_session(db, current_user.id, "text").id
    try:
        return handle_turn(db, session_id, current_user.id, body.message.strip())
    except SupportError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e) else 503, detail=str(e))
    except Exception as e:
        logger.error(f"Support chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="The support bot failed to respond. Please try again.")


@router.get("/orders")
async def my_orders(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The current customer's orders (shown in the support side panel)."""
    return list_recent_orders(ToolContext(db=db, user_id=current_user.id), limit=20)["orders"]


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(body: FeedbackRequest, current_user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """Submit the satisfaction form for a support conversation."""
    if body.session_id is not None and not db.query(ChatSession).filter(
            ChatSession.id == body.session_id, ChatSession.owner_id == current_user.id).first():
        raise HTTPException(status_code=404, detail="Session not found")
    fb = Feedback(session_id=body.session_id, user_id=current_user.id, channel=body.channel,
                  rating=body.rating, resolved=body.resolved, comment=body.comment)
    db.add(fb)
    db.commit()
    return {"id": fb.id, "message": "Thanks for your feedback!"}


@router.get("/tickets")
async def list_tickets(status_filter: Optional[str] = None, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Human-agent queue of escalated conversations, most urgent first."""
    query = db.query(SupportTicket, User).join(User, User.id == SupportTicket.user_id)
    if status_filter:
        query = query.filter(SupportTicket.status == status_filter)
    rows = query.all()
    rows.sort(key=lambda r: (r[0].status == "resolved", PRIORITY_ORDER.get(r[0].priority, 9), -r[0].id))
    return [{"id": t.id, "customer": u.name, "customer_phone": u.phone_number, "session_id": t.session_id,
             "channel": t.channel, "reason": t.reason, "priority": t.priority, "sentiment_score": t.sentiment_score,
             "summary": t.summary, "status": t.status, "created_at": t.created_at} for t, u in rows]


@router.patch("/tickets/{ticket_id}")
async def update_ticket(ticket_id: int, body: TicketUpdate, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket.status = body.status
    db.commit()
    return {"id": ticket.id, "status": ticket.status}


@router.get("/metrics")
async def metrics(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Evaluation metrics: intent accuracy, appropriateness, response time, satisfaction, plus distributions."""
    return compute_metrics(db)
