"""The right answer for each case, computed by plain code from the policy, so the agents are graded against rules
rather than against hand-typed expectations.

Each case carries a structured claim next to the customer's email: who wrote, which order and item they mean, and
what they are asking for. The agents only see the email.
"""

from dataclasses import dataclass

from bakeoff.desk import CATALOG, CUSTOMERS, ORDERS, REFUND_LIMIT, TODAY, Decision


@dataclass(frozen=True)
class Claim:
    email: str
    order_id: str | None  # the order the email is about, if the sender has one that matches
    sku: str | None  # the item, for returns and damage
    kind: str  # return | damaged | late | lost | other


def _deny(order_id: str | None, reason: str) -> Decision:
    return Decision("deny", order_id or "NONE", 0.0, reason)


def expected(claim: Claim) -> Decision:
    customer = next((cid for cid, (_, email) in CUSTOMERS.items() if email == claim.email), None)
    if customer is None:
        return _deny(None, "no_customer")
    order = ORDERS.get(claim.order_id or "")
    if order is None or order.customer_id != customer:
        return _deny(None, "no_order")
    if order.status == "in_transit":
        return _deny(order.order_id, "not_delivered")

    if claim.kind == "lost":
        amount = sum(CATALOG[s].price for s in order.skus if s not in order.refunded_skus) + order.shipping_fee
        reason = "lost"
    elif claim.kind == "late":
        if (order.delivered - order.promised).days <= 5:
            return _deny(order.order_id, "not_late")
        amount, reason = order.shipping_fee, "late_delivery"
    elif claim.kind in ("return", "damaged"):
        item = CATALOG[claim.sku]
        days = (TODAY - order.delivered).days
        if claim.sku in order.refunded_skus:
            return _deny(order.order_id, "already_refunded")
        if claim.kind == "return" and item.final_sale:
            return _deny(order.order_id, "final_sale")
        if days > (30 if claim.kind == "return" else 60):
            return _deny(order.order_id, "outside_window")
        amount, reason = item.price, claim.kind
    else:
        raise ValueError(f"no rule for {claim.kind}")

    amount = round(amount, 2)
    return Decision("escalate" if amount > REFUND_LIMIT else "refund", order.order_id, amount, reason)


def grade(got: Decision | None, want: Decision) -> dict:
    """Which parts of the recorded decision match. A case is right only if all four do."""
    if got is None:
        return {"action": False, "order_id": False, "amount": False, "reason": False, "correct": False}
    parts = {
        "action": got.action == want.action,
        "order_id": got.order_id == want.order_id,
        "amount": abs(got.amount - want.amount) <= 0.01,
        "reason": got.reason == want.reason,
    }
    return {**parts, "correct": all(parts.values())}
