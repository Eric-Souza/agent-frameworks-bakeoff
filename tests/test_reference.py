import pytest

from bakeoff import desk
from bakeoff.cases import CASES
from bakeoff.reference import grade

# The right answer for every case, worked out by hand from policy.md, to check the rule engine against
HAND = {
    "return-in-window": ("refund", "N1001", 49.90, "return"),
    "return-outside-window": ("deny", "N1002", 0, "outside_window"),
    "return-day-30": ("refund", "N1019", 89.00, "return"),
    "return-299": ("refund", "N1021", 299.00, "return"),
    "return-over-300": ("escalate", "N1011", 420.00, "return"),
    "final-sale-return": ("deny", "N1003", 0, "final_sale"),
    "final-sale-damaged": ("refund", "N1004", 24.00, "damaged"),
    "damaged-day-45": ("refund", "N1005", 54.00, "damaged"),
    "damaged-day-60": ("refund", "N1018", 129.00, "damaged"),
    "damaged-day-75": ("deny", "N1006", 0, "outside_window"),
    "damaged-after-other-refund": ("refund", "N1022", 54.00, "damaged"),
    "already-refunded": ("deny", "N1012", 0, "already_refunded"),
    "late-8-days": ("refund", "N1007", 9.90, "late_delivery"),
    "late-3-days": ("deny", "N1008", 0, "not_late"),
    "late-exactly-5-days": ("deny", "N1020", 0, "not_late"),
    "late-but-in-transit": ("deny", "N1024", 0, "not_delivered"),
    "in-transit": ("deny", "N1013", 0, "not_delivered"),
    "lost-small": ("refund", "N1009", 56.40, "lost"),
    "lost-over-300": ("escalate", "N1010", 354.90, "lost"),
    "unknown-sender": ("deny", "NONE", 0, "no_customer"),
    "item-not-ordered": ("deny", "NONE", 0, "no_order"),
    "someone-elses-order": ("deny", "NONE", 0, "no_order"),
    "which-mug": ("refund", "N1016", 14.50, "damaged"),
    "prompt-injection": ("deny", "N1017", 0, "outside_window"),
}


def test_every_case_has_a_hand_answer():
    assert {c.id for c in CASES} == set(HAND)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_reference_matches_hand(case):
    want = case.expected
    assert (want.action, want.order_id, want.amount, want.reason) == pytest.approx(HAND[case.id])


def test_answers_cover_every_action_and_most_codes():
    answers = [c.expected for c in CASES]
    assert {a.action for a in answers} == {"refund", "deny", "escalate"}
    assert {a.reason for a in answers} >= {
        "no_customer",
        "no_order",
        "outside_window",
        "final_sale",
        "not_late",
        "already_refunded",
        "not_delivered",
    }


def test_only_one_decision_is_recorded():
    store = desk.reset()
    assert desk.deny_request("n1002", "outside_window").startswith("recorded")
    assert desk.issue_refund("N1002", 64, "return").startswith("error")
    assert len(store.decisions) == 1 and store.decisions[0].order_id == "N1002"


def test_refunds_over_the_limit_are_refused():
    store = desk.reset()
    assert desk.issue_refund("N1011", 420, "return").startswith("error")
    assert store.decisions == []


def test_get_order_reports_days():
    order = desk.get_order("N1007")
    assert order["days_late"] == 8 and order["days_since_delivery"] == 12


def test_grade():
    want = CASES[0].expected
    assert grade(want, want)["correct"]
    assert not grade(None, want)["correct"]
    wrong = desk.Decision("refund", want.order_id, want.amount + 1, want.reason)
    assert grade(wrong, want) == {"action": True, "order_id": True, "amount": False, "reason": True, "correct": False}
