"""
Seed demo e-commerce data for the customer support bot.

Creates (idempotently):
  - the demo customer from the README (phone 9876543210, password Test123456!@)
  - a product catalog
  - 8 orders in different states for the demo customer (ORD-10021 .. ORD-10028)
  - the "Support Bot" agent with the FAQ (data/faq.md) loaded as an embedded document

Usage (from the backend directory):
    python seed_ecommerce.py                     # demo customer
    python seed_ecommerce.py --phone 7276072343  # also give an existing account its own demo orders
    python seed_ecommerce.py --reload-faq        # re-embed data/faq.md after editing it
    python seed_ecommerce.py --reset             # restore demo orders (undo cancellations/returns) before a demo
    python seed_ecommerce.py --clear-logs        # delete all support conversations, tickets and feedback
"""
import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal, ensure_schema
from app.models import (Agent, AgentDocument, ChatSession, Chunk, Document, Embedding, Feedback, MessageAnalysis, Order,
                        OrderItem, Product, ReturnRequest, SupportTicket, User)

DEMO_PHONE = "9876543210"
DEMO_PASSWORD = "Test123456!@"
FAQ_PATH = Path(__file__).parent / "data" / "faq.md"

PRODUCTS = [
    ("ELE-001", "SoundWave Pro Wireless Headphones", "Electronics", 3499, 42, "Over-ear Bluetooth headphones with active noise cancellation and 30-hour battery."),
    ("ELE-002", "PulseFit Smartwatch S2", "Electronics", 4999, 18, "AMOLED smartwatch with heart-rate, SpO2, GPS and 7-day battery."),
    ("ELE-003", "ClickPro Wireless Mouse", "Electronics", 799, 120, "Silent-click 2.4 GHz wireless mouse with 18-month battery."),
    ("ELE-004", "BoltCharge 20000mAh Power Bank", "Electronics", 1599, 0, "20W fast-charging power bank with USB-C PD."),
    ("ELE-005", "VibeBuds TWS Earbuds", "Electronics", 1999, 65, "True wireless earbuds with ENC mic and 40-hour total playback."),
    ("ELE-006", "ArmorShield Phone Case", "Accessories", 499, 200, "Shockproof transparent case with raised camera edges."),
    ("ELE-007", "UltraView 24-inch Monitor", "Electronics", 10999, 9, "24-inch IPS full-HD monitor, 75 Hz, with HDMI and VGA."),
    ("FAS-001", "StrideMax Running Shoes", "Footwear", 2799, 30, "Lightweight mesh running shoes with cushioned sole."),
    ("FAS-002", "Urban Denim Jacket", "Clothing", 2199, 25, "Classic blue denim jacket, regular fit."),
    ("FAS-003", "Cotton Crew T-Shirt (Pack of 3)", "Clothing", 899, 150, "100% cotton round-neck t-shirts in black, white and grey."),
    ("FAS-004", "TrailPack 30L Laptop Backpack", "Bags", 1899, 55, "Water-resistant backpack with padded 15.6-inch laptop sleeve."),
    ("HOM-001", "BrewMaster Drip Coffee Maker", "Home & Kitchen", 3299, 14, "1.2 L drip coffee maker with keep-warm plate."),
    ("HOM-002", "AirPure Mini Air Purifier", "Home & Kitchen", 6499, 7, "HEPA H13 air purifier for rooms up to 300 sq ft."),
    ("HOM-003", "ChefPro Non-stick Cookware Set", "Home & Kitchen", 2599, 22, "3-piece induction-friendly non-stick cookware set."),
    ("HOM-004", "SteelFlask 1L Water Bottle", "Home & Kitchen", 649, 300, "Vacuum-insulated stainless steel bottle, hot 12 h / cold 24 h."),
    ("BOO-001", "Atomic Habits (Paperback)", "Books", 399, 80, "James Clear's bestseller on building good habits."),
    ("BEA-001", "GlowCare Vitamin C Serum", "Beauty", 599, 90, "10% vitamin C face serum, 30 ml."),
    ("SPO-001", "FlexCore Yoga Mat 6mm", "Sports", 899, 60, "Anti-slip TPE yoga mat with carry strap."),
    ("SPO-002", "PowerGrip Adjustable Dumbbells", "Sports", 4499, 11, "Pair of adjustable dumbbells, 2.5–12 kg each."),
    ("TOY-001", "BuildIt 500-Piece Brick Set", "Toys", 1499, 33, "Creative building bricks set for ages 6+."),
]

# (suffix, status, days_ago_placed, delivered_days_ago, [(sku, qty)], carrier)
ORDERS = [
    (21, "delivered", 9, 5, [("ELE-001", 1), ("ELE-006", 1)], "Delhivery"),
    (22, "delivered", 50, 45, [("FAS-001", 1)], "Ekart"),
    (23, "shipped", 3, None, [("ELE-002", 1)], "BlueDart"),
    (24, "placed", 0, None, [("HOM-002", 1), ("HOM-004", 2)], None),
    (25, "out_for_delivery", 4, None, [("FAS-002", 1), ("FAS-003", 1)], "Delhivery"),
    (26, "cancelled", 20, None, [("ELE-004", 1)], None),
    (27, "delivered", 16, 12, [("HOM-001", 1)], "Ekart"),
    (28, "delivered", 6, 3, [("FAS-004", 1), ("ELE-003", 1)], "BlueDart"),
]


def get_or_create_demo_user(db) -> User:
    user = db.query(User).filter(User.phone_number == DEMO_PHONE).first()
    if not user:
        user = User(phone_number=DEMO_PHONE, name="Demo Customer", hashed_password=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.commit()
        print(f"Created demo user {DEMO_PHONE} / {DEMO_PASSWORD}")
    return user


def seed_products(db) -> dict:
    by_sku = {p.sku: p for p in db.query(Product).all()}
    for sku, name, category, price, stock, desc in PRODUCTS:
        if sku not in by_sku:
            p = Product(sku=sku, name=name, category=category, price=price, stock=stock, description=desc)
            db.add(p)
            by_sku[sku] = p
    db.commit()
    return by_sku


def seed_orders(db, user: User, prefix: str, products: dict) -> None:
    now = datetime.now(timezone.utc)
    created = 0
    for suffix, status, placed_ago, delivered_ago, items, carrier in ORDERS:
        number = f"ORD-{prefix}{suffix:02d}"
        if db.query(Order).filter(Order.order_number == number).first():
            continue
        placed = now - timedelta(days=placed_ago, hours=3)
        shipped = placed + timedelta(days=1) if status in ("shipped", "out_for_delivery", "delivered") else None
        order = Order(
            order_number=number, user_id=user.id, status=status, created_at=placed, shipped_at=shipped,
            delivered_at=now - timedelta(days=delivered_ago) if delivered_ago is not None else None,
            expected_delivery=(now + timedelta(days=2)) if status == "shipped" else
                              (now + timedelta(hours=6)) if status == "out_for_delivery" else
                              (placed + timedelta(days=5)) if status == "placed" else None,
            carrier=carrier, tracking_number=f"{carrier[:2].upper()}{abs(hash(number)) % 10**10:010d}" if carrier else None,
            total=sum(products[sku].price * qty for sku, qty in items),
        )
        order.items = [OrderItem(product_id=products[sku].id, quantity=qty, unit_price=products[sku].price)
                       for sku, qty in items]
        db.add(order)
        created += 1
    db.commit()

    # One existing return so "what's the status of my return" has something to find
    coffee_order = db.query(Order).filter(Order.order_number == f"ORD-{prefix}27").first()
    if coffee_order and not db.query(ReturnRequest).filter(ReturnRequest.order_id == coffee_order.id).first():
        db.add(ReturnRequest(order_id=coffee_order.id, user_id=user.id, product_id=products["HOM-001"].id,
                             reason="Glass carafe arrived cracked", status="approved"))
        db.commit()
    print(f"Orders for {user.phone_number}: {created} created (ORD-{prefix}21 .. ORD-{prefix}28)")


def reset_orders(db, user: User, prefix: str) -> None:
    """Delete the demo orders (and their returns) so seed_orders recreates them in their original state."""
    numbers = [f"ORD-{prefix}{suffix:02d}" for suffix, *_ in ORDERS]
    orders = db.query(Order).filter(Order.user_id == user.id, Order.order_number.in_(numbers)).all()
    for order in orders:
        db.query(ReturnRequest).filter(ReturnRequest.order_id == order.id).delete()
        db.delete(order)
    db.commit()


def clear_support_logs(db) -> None:
    """Remove support conversations (messages and analysis cascade), tickets and feedback."""
    db.query(Feedback).delete()
    db.query(SupportTicket).delete()
    db.query(MessageAnalysis).delete()  # SQLite doesn't enforce ON DELETE CASCADE by default
    sessions = db.query(ChatSession).filter(ChatSession.channel.isnot(None)).all()
    for session in sessions:
        db.delete(session)
    db.commit()
    print(f"Cleared {len(sessions)} support conversations, all tickets and feedback")


def faq_sections(text: str) -> list[str]:
    """Split the FAQ markdown into one chunk per question."""
    parts = re.split(r"\n(?=## )", text)
    return [p.strip().lstrip("#").strip() for p in parts if p.strip().startswith("## ")]


def seed_faq(db, owner: User, reload: bool) -> None:
    agent = db.query(Agent).filter(Agent.name == settings.SUPPORT_AGENT_NAME).first()
    if agent and not reload:
        print("FAQ already loaded (use --reload-faq to re-embed)")
        return
    if not agent:
        agent = Agent(user_id=owner.id, name=settings.SUPPORT_AGENT_NAME, ai_model=settings.SUPPORT_MODEL,
                      system_prompt="ShopEase customer support FAQ knowledge base.")
        db.add(agent)
        db.flush()

    # Replace any previously linked FAQ document
    for link in db.query(AgentDocument).filter(AgentDocument.agent_id == agent.id).all():
        doc = db.get(Document, link.document_id)
        db.delete(link)
        if doc:
            db.delete(doc)
    db.flush()

    text = FAQ_PATH.read_text(encoding="utf-8")
    doc = Document(user_id=owner.id, original_name="faq.md", file_path=str(FAQ_PATH.relative_to(Path(__file__).parent)),
                   file_size=len(text.encode()), is_processed=True)
    db.add(doc)
    db.flush()
    db.add(AgentDocument(agent_id=agent.id, document_id=doc.id))

    from app.services.chat_service import embed_text
    embedded = 0
    for i, section in enumerate(faq_sections(text)):
        chunk = Chunk(document_id=doc.id, text=section, chunk_index=i)
        db.add(chunk)
        db.flush()
        try:
            db.add(Embedding(chunk_id=chunk.id, vector=embed_text(section)))
            embedded += 1
        except Exception as e:
            print(f"  Embedding skipped for chunk {i} ({e}); keyword search will be used")
    db.commit()
    print(f"FAQ loaded: {i + 1} sections, {embedded} embedded, agent '{agent.name}' (id {agent.id})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phone", action="append", default=[], help="Existing account to also give demo orders")
    parser.add_argument("--reload-faq", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Restore demo orders to their original state")
    parser.add_argument("--clear-logs", action="store_true", help="Delete support conversations, tickets and feedback")
    args = parser.parse_args()

    ensure_schema()
    db = SessionLocal()
    try:
        if args.clear_logs:
            clear_support_logs(db)
        demo = get_or_create_demo_user(db)
        products = seed_products(db)
        print(f"Products: {len(products)}")
        customers = [(demo, "100")]
        for phone in args.phone:
            user = db.query(User).filter(User.phone_number == phone).first()
            if not user:
                print(f"No user with phone {phone}; register first")
                continue
            customers.append((user, f"2{user.id:02d}"))
        for user, prefix in customers:
            if args.reset:
                reset_orders(db, user, prefix)
            seed_orders(db, user, prefix, products)
        seed_faq(db, demo, args.reload_faq)
    finally:
        db.close()


if __name__ == "__main__":
    main()
