"""
Support tools: the database actions the bot can take on behalf of a customer.

Every function is scoped to ctx.user_id, so a customer can never read or change another
customer's orders. The same functions back the text chat (OpenAI tool calling in engine.py)
and the LiveKit voice agent (voice_agent/agent.py).
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Agent, Chunk, Embedding, AgentDocument, Order, OrderItem, Product, ReturnRequest, SupportTicket
from app.support.nlp import normalize_order_number

logger = logging.getLogger(__name__)

RETURN_WINDOW_DAYS = 30


@dataclass
class ToolContext:
    db: Session
    user_id: int
    session_id: Optional[int] = None
    channel: str = "text"
    sentiment_score: Optional[float] = None


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt_date(dt: Optional[datetime]) -> Optional[str]:
    return _aware(dt).strftime("%d %b %Y") if dt else None


def _find_order(ctx: ToolContext, order_number: str) -> Optional[Order]:
    normalized = normalize_order_number(order_number or "")
    if not normalized:
        return None
    return ctx.db.query(Order).filter(Order.order_number == normalized, Order.user_id == ctx.user_id).first()


def _order_summary(order: Order) -> Dict:
    return {
        "order_number": order.order_number,
        "status": order.status,
        "placed_on": _fmt_date(order.created_at),
        "shipped_on": _fmt_date(order.shipped_at),
        "delivered_on": _fmt_date(order.delivered_at),
        "expected_delivery": _fmt_date(order.expected_delivery),
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
        "total": order.total,
        "items": [{"product": i.product.name, "quantity": i.quantity, "unit_price": i.unit_price} for i in order.items],
    }


def get_order_status(ctx: ToolContext, order_number: str) -> Dict:
    """Look up the status, delivery dates and items of one of the customer's orders."""
    order = _find_order(ctx, order_number)
    if not order:
        return {"found": False, "message": f"No order {order_number} was found on this account."}
    return {"found": True, **_order_summary(order)}


def list_recent_orders(ctx: ToolContext, limit: int = 5) -> Dict:
    """List the customer's most recent orders."""
    orders = (ctx.db.query(Order).filter(Order.user_id == ctx.user_id)
              .order_by(Order.created_at.desc()).limit(limit).all())
    return {"orders": [_order_summary(o) for o in orders]}


def search_products(ctx: ToolContext, query: str) -> Dict:
    """Search the catalog by name, category or description."""
    terms = [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 2] or [query or ""]
    filters = []
    for t in terms:
        like = f"%{t}%"
        filters += [Product.name.ilike(like), Product.category.ilike(like), Product.description.ilike(like)]
    products = ctx.db.query(Product).filter(or_(*filters)).limit(5).all()
    return {"products": [
        {"name": p.name, "sku": p.sku, "category": p.category, "price": p.price,
         "in_stock": p.stock > 0, "stock": p.stock, "description": p.description}
        for p in products
    ]}


def _match_item(order: Order, product: Optional[str]) -> Optional[OrderItem]:
    if not order.items:
        return None
    if not product:
        return order.items[0] if len(order.items) == 1 else None
    scored = [(SequenceMatcher(None, product.lower(), i.product.name.lower()).ratio()
               + (0.5 if product.lower() in i.product.name.lower() else 0), i) for i in order.items]
    score, item = max(scored, key=lambda s: s[0])
    return item if score >= 0.35 else None


def create_return_request(ctx: ToolContext, order_number: str, reason: str, product: Optional[str] = None) -> Dict:
    """Create a return request for a delivered item within the 30-day return window."""
    order = _find_order(ctx, order_number)
    if not order:
        return {"success": False, "message": f"No order {order_number} was found on this account."}
    if order.status != "delivered":
        return {"success": False, "message": f"Order {order.order_number} is '{order.status}'. Only delivered orders can be returned."}

    delivered = _aware(order.delivered_at)
    if delivered and datetime.now(timezone.utc) - delivered > timedelta(days=RETURN_WINDOW_DAYS):
        return {"success": False, "message": f"Order {order.order_number} was delivered on {_fmt_date(delivered)}, "
                                             f"outside the {RETURN_WINDOW_DAYS}-day return window."}

    item = _match_item(order, product)
    if item is None:
        return {"success": False, "needs_clarification": True,
                "message": "Which item would you like to return?",
                "items": [i.product.name for i in order.items]}

    existing = ctx.db.query(ReturnRequest).filter(
        ReturnRequest.order_id == order.id, ReturnRequest.product_id == item.product_id,
        ReturnRequest.status.in_(["requested", "approved"])).first()
    if existing:
        return {"success": False, "message": f"A return for {item.product.name} already exists (return #{existing.id}, status {existing.status})."}

    ret = ReturnRequest(order_id=order.id, user_id=ctx.user_id, product_id=item.product_id,
                        reason=reason or "Not specified", status="requested")
    ctx.db.add(ret)
    ctx.db.flush()
    return {"success": True, "return_id": ret.id, "product": item.product.name, "order_number": order.order_number,
            "message": f"Return #{ret.id} created for {item.product.name}. A pickup will be scheduled within 2 business days "
                       f"and the refund of ₹{item.unit_price * item.quantity:,.0f} is issued after inspection."}


def cancel_order(ctx: ToolContext, order_number: str) -> Dict:
    """Cancel an order that has not shipped yet."""
    order = _find_order(ctx, order_number)
    if not order:
        return {"success": False, "message": f"No order {order_number} was found on this account."}
    if order.status == "cancelled":
        return {"success": False, "message": f"Order {order.order_number} is already cancelled."}
    if order.status != "placed":
        return {"success": False, "message": f"Order {order.order_number} is already '{order.status}' and can't be cancelled. "
                                             "You can request a return once it is delivered."}
    order.status = "cancelled"
    ctx.db.flush()
    return {"success": True, "message": f"Order {order.order_number} has been cancelled. The refund of ₹{order.total:,.0f} "
                                        "will reach the original payment method in 5-7 business days."}


def search_faq(ctx: ToolContext, question: str, top_k: int = 3) -> Dict:
    """Search the store FAQ / policy knowledge base."""
    agent = ctx.db.query(Agent).filter(Agent.name == settings.SUPPORT_AGENT_NAME).first()
    if not agent:
        return {"passages": [], "message": "FAQ knowledge base is not loaded. Run seed_ecommerce.py."}

    passages: List[str] = []
    try:
        from app.services.chat_service import embed_text, find_similar_chunks
        chunks = find_similar_chunks(embed_text(question), agent.id, ctx.db, top_k=top_k)
        passages = [c["text"] for c in chunks]
    except Exception as e:
        logger.warning(f"Embedding FAQ search failed, using keyword search: {e}")

    if not passages:
        # Keyword overlap fallback (works without the OpenAI API)
        words = set(re.findall(r"\w{4,}", question.lower()))
        rows = (ctx.db.query(Chunk.text).join(AgentDocument, AgentDocument.document_id == Chunk.document_id)
                .filter(AgentDocument.agent_id == agent.id).all())
        scored = sorted(((len(words & set(re.findall(r"\w{4,}", t.lower()))), t) for (t,) in rows), reverse=True)
        passages = [t for s, t in scored[:top_k] if s > 0]
    return {"passages": passages}


PRIORITY_BY_SENTIMENT = [(-0.8, "urgent"), (-0.5, "high"), (-0.1, "normal")]


def priority_for(sentiment_score: Optional[float]) -> str:
    if sentiment_score is None:
        return "normal"
    for threshold, priority in PRIORITY_BY_SENTIMENT:
        if sentiment_score <= threshold:
            return priority
    return "low"


def escalate_to_human(ctx: ToolContext, reason: str, summary: str = "") -> Dict:
    """Hand the conversation to a human agent by creating (or reusing) a support ticket."""
    if ctx.session_id:
        existing = ctx.db.query(SupportTicket).filter(
            SupportTicket.session_id == ctx.session_id, SupportTicket.status != "resolved").first()
        if existing:
            return {"ticket_id": existing.id, "priority": existing.priority, "already_open": True,
                    "message": f"Ticket #{existing.id} is already open; a human agent will contact you."}
    ticket = SupportTicket(
        user_id=ctx.user_id, session_id=ctx.session_id, channel=ctx.channel, reason=reason[:200],
        priority=priority_for(ctx.sentiment_score), sentiment_score=ctx.sentiment_score,
        summary=summary or reason, status="open",
    )
    ctx.db.add(ticket)
    ctx.db.flush()
    eta = "within 15 minutes" if ticket.priority in ("urgent", "high") else "within 2 hours"
    return {"ticket_id": ticket.id, "priority": ticket.priority,
            "message": f"Ticket #{ticket.id} created with {ticket.priority} priority. A human agent will contact you {eta}."}


# OpenAI tool definitions for the text-chat engine
TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "get_order_status", "description": "Get status, tracking and delivery details of one of the customer's orders.",
        "parameters": {"type": "object", "properties": {"order_number": {"type": "string", "description": "e.g. ORD-10023"}},
                       "required": ["order_number"]}}},
    {"type": "function", "function": {
        "name": "list_recent_orders", "description": "List the customer's recent orders. Use when they don't know the order number.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "search_products", "description": "Search the product catalog for price, stock and details.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "create_return_request", "description": "Create a return/refund request for an item from a delivered order.",
        "parameters": {"type": "object", "properties": {
            "order_number": {"type": "string"}, "reason": {"type": "string"},
            "product": {"type": "string", "description": "Name of the item to return, if the order has several"}},
            "required": ["order_number", "reason"]}}},
    {"type": "function", "function": {
        "name": "cancel_order", "description": "Cancel an order that has not shipped yet.",
        "parameters": {"type": "object", "properties": {"order_number": {"type": "string"}}, "required": ["order_number"]}}},
    {"type": "function", "function": {
        "name": "search_faq", "description": "Search store policies and FAQs (shipping, returns, refunds, payments, warranty, account).",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "escalate_to_human", "description": "Hand over to a human agent when the customer asks for one or the issue can't be solved.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}, "summary": {"type": "string", "description": "Short summary of the issue for the agent"}},
            "required": ["reason"]}}},
]

TOOL_FUNCTIONS = {
    "get_order_status": get_order_status,
    "list_recent_orders": list_recent_orders,
    "search_products": search_products,
    "create_return_request": create_return_request,
    "cancel_order": cancel_order,
    "search_faq": search_faq,
    "escalate_to_human": escalate_to_human,
}


def run_tool(ctx: ToolContext, name: str, args: Dict) -> Dict:
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"Unknown tool {name}"}
    try:
        return func(ctx, **args)
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
