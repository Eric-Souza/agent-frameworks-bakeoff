"""The refund desk all three frameworks run: customers, orders, the tools the agents get, and the decision they make.

The tools are plain functions over one in-memory store, so every framework wraps the same code. The store is reset
before each case, and the decision the reviewer records through a tool is what gets graded, not what the agents
say in the chat.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

TODAY = date(2026, 11, 2)
POLICY = (Path(__file__).parent / "policy.md").read_text(encoding="utf-8")
REFUND_LIMIT = 300.00


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: float
    final_sale: bool = False


CATALOG = {
    p.sku: p
    for p in [
        Product("K1", "Gooseneck kettle", 49.90),
        Product("M1", "Stoneware mug", 14.50),
        Product("J1", "Rain jacket (clearance)", 79.00, final_sale=True),
        Product("E1", "Espresso machine", 420.00),
        Product("L1", "Desk lamp", 64.00),
        Product("B1", "Bamboo cutting board", 32.00),
        Product("S1", "Linen sheet set", 129.00),
        Product("V1", "Robot vacuum", 299.00),
        Product("C1", "Cast-iron skillet", 54.00),
        Product("P1", "Throw pillow (final sale)", 24.00, final_sale=True),
        Product("T1", "Tea set", 89.00),
        Product("R1", "Wool area rug", 340.00),
        Product("H1", "Wireless headphones", 189.00),
        Product("G1", "Glass storage set", 45.00),
    ]
}

CUSTOMERS = {
    f"c{i:02d}": (name, f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.com")
    for i, name in enumerate(
        [
            "Ana Silva",
            "Ben Okafor",
            "Chloe Martin",
            "Diego Ramos",
            "Emma Wright",
            "Farah Haddad",
            "George Chen",
            "Hana Sato",
            "Ivan Petrov",
            "Julia Costa",
            "Kofi Mensah",
            "Lena Fischer",
        ],
        start=1,
    )
}


@dataclass
class Order:
    order_id: str
    customer_id: str
    placed: date
    promised: date
    delivered: date | None
    status: str  # delivered | in_transit | lost
    shipping_fee: float
    skus: list[str]
    refunded_skus: list[str] = field(default_factory=list)


def _order(oid, cid, *, promised, delivered=None, status="delivered", shipping=9.90, skus, refunded=()):
    placed = promised - timedelta(days=5)
    return Order(oid, cid, placed, promised, delivered, status, shipping, list(skus), list(refunded))


ORDERS = {
    o.order_id: o
    for o in [
        _order("N1001", "c01", promised=ago(13), delivered=ago(12), skus=["K1", "B1"]),
        _order("N1002", "c02", promised=ago(42), delivered=ago(41), skus=["L1"]),
        _order("N1003", "c03", promised=ago(9), delivered=ago(8), skus=["J1", "M1"]),
        _order("N1004", "c04", promised=ago(21), delivered=ago(20), skus=["P1"]),
        _order("N1005", "c05", promised=ago(46), delivered=ago(45), skus=["C1"]),
        _order("N1006", "c06", promised=ago(76), delivered=ago(75), skus=["T1"]),
        _order("N1007", "c07", promised=ago(20), delivered=ago(12), skus=["G1"]),
        _order("N1008", "c08", promised=ago(10), delivered=ago(7), shipping=14.90, skus=["B1"]),
        _order("N1009", "c09", promised=ago(6), status="lost", skus=["M1", "B1"]),
        _order("N1010", "c10", promised=ago(8), status="lost", shipping=14.90, skus=["R1"]),
        _order("N1011", "c11", promised=ago(10), delivered=ago(9), skus=["E1"]),
        _order("N1012", "c12", promised=ago(16), delivered=ago(15), skus=["H1"], refunded=["H1"]),
        _order("N1013", "c01", promised=TODAY + timedelta(days=4), status="in_transit", skus=["S1"]),
        _order("N1015", "c05", promised=ago(51), delivered=ago(50), skus=["M1"]),
        _order("N1016", "c05", promised=ago(7), delivered=ago(6), skus=["M1", "G1"]),
        _order("N1017", "c07", promised=ago(45), delivered=ago(44), skus=["L1"]),
        _order("N1018", "c08", promised=ago(61), delivered=ago(60), skus=["S1"]),
        _order("N1019", "c09", promised=ago(31), delivered=ago(30), skus=["T1"]),
        _order("N1020", "c10", promised=ago(15), delivered=ago(10), skus=["K1"]),
        _order("N1021", "c11", promised=ago(6), delivered=ago(5), skus=["V1"]),
        _order("N1022", "c12", promised=ago(26), delivered=ago(25), skus=["G1", "C1"], refunded=["G1"]),
        _order("N1024", "c04", promised=ago(3), status="in_transit", skus=["H1"]),
    ]
}


@dataclass
class Decision:
    action: str  # refund | deny | escalate
    order_id: str
    amount: float
    reason: str


@dataclass
class Store:
    decisions: list[Decision] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)


# One case runs at a time, and some frameworks run tools on worker threads, so this is a plain module global
# rather than a contextvar
_store = Store()


def reset() -> Store:
    global _store
    _store = Store()
    return _store


def _log(name: str) -> None:
    _store.tool_calls.append(name)


# The tools. Docstrings and type hints are what each framework turns into the tool schema the model sees.

READ_TOOLS: list = []  # the investigator's
ACTION_TOOLS: list = []  # the reviewer's, with get_order to check the facts it was handed


def _read(fn):
    READ_TOOLS.append(fn)
    return fn


def _action(fn):
    ACTION_TOOLS.append(fn)
    return fn


@_read
def find_customer(email: str) -> dict:
    """Look up a customer by email address. Returns their customer id and name, or an error."""
    _log("find_customer")
    for cid, (name, address) in CUSTOMERS.items():
        if address == email.strip().lower():
            return {"customer_id": cid, "name": name}
    return {"error": f"no customer with email {email}"}


@_read
def list_orders(customer_id: str) -> list[dict] | dict:
    """List a customer's orders: id, status, delivery date and the items in each."""
    _log("list_orders")
    if customer_id not in CUSTOMERS:
        return {"error": f"no customer {customer_id}"}
    return [
        {
            "order_id": o.order_id,
            "status": o.status,
            "delivered": o.delivered.isoformat() if o.delivered else None,
            "items": [CATALOG[s].name for s in o.skus],
        }
        for o in ORDERS.values()
        if o.customer_id == customer_id
    ]


@_read
def get_order(order_id: str) -> dict:
    """Get one order in full: its customer, dates, how many days ago it was delivered and how late, shipping fee,
    items with price and final-sale flag, and which items were already refunded."""
    _log("get_order")
    o = ORDERS.get(order_id.strip().upper())
    if not o:
        return {"error": f"no order {order_id}"}
    return {
        "order_id": o.order_id,
        "customer_id": o.customer_id,
        "status": o.status,
        "placed": o.placed.isoformat(),
        "promised": o.promised.isoformat(),
        "delivered": o.delivered.isoformat() if o.delivered else None,
        "days_since_delivery": (TODAY - o.delivered).days if o.delivered else None,
        "days_late": (o.delivered - o.promised).days if o.delivered else None,
        "shipping_fee": o.shipping_fee,
        "items": [
            {"sku": s, "name": CATALOG[s].name, "price": CATALOG[s].price, "final_sale": CATALOG[s].final_sale}
            for s in o.skus
        ],
        "refunded_skus": list(o.refunded_skus),
    }


def _decide(action: str, order_id: str, amount: float, reason: str) -> str:
    if _store.decisions:
        return "error: a decision was already recorded for this request"
    _store.decisions.append(Decision(action, order_id.strip().upper(), round(float(amount), 2), reason.strip()))
    return f"recorded: {action} {order_id} {amount:.2f} {reason}"


@_action
def issue_refund(order_id: str, amount: float, reason: str) -> str:
    """Issue a refund of `amount` dollars on an order, with a reason code from the policy. Final: call once."""
    _log("issue_refund")
    if amount > REFUND_LIMIT:
        return f"error: refunds above {REFUND_LIMIT:.2f} must be escalated"
    return _decide("refund", order_id, amount, reason)


@_action
def deny_request(order_id: str, reason: str) -> str:
    """Deny the request with a reason code from the policy. Use order id 'none' if there is no matching order."""
    _log("deny_request")
    return _decide("deny", order_id, 0.0, reason)


@_action
def escalate(order_id: str, amount: float, reason: str) -> str:
    """Hand a refund above $300 to a human, with the amount and reason code it would have had. Final: call once."""
    _log("escalate")
    return _decide("escalate", order_id, amount, reason)


INVESTIGATOR_TOOLS = READ_TOOLS
REVIEWER_TOOLS = [get_order, *ACTION_TOOLS]
ACTION_NAMES = [fn.__name__ for fn in ACTION_TOOLS]
