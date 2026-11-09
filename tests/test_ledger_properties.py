"""Small deterministic property and metamorphic pilot for the existing ledger aggregate."""
from hypothesis import given, settings, strategies as st

from app.routers.long_term_details import aggregate


def day(expenses=(), meals=(), date="2026-11-09"):
    return {
        "date": date, "activities": [], "expenses": list(expenses), "meals": list(meals),
        "attention_items": [], "legacy_attention": [], "attention_confirmed": False,
        "recorded": False, "expense_confirmed": False, "day_confirmed": False,
    }


expense_rows = st.lists(
    st.tuples(
        st.sampled_from(("food", "snacks", "shopping")),
        st.sampled_from(("expense", "refund")),
        st.integers(min_value=0, max_value=100_000),
    ),
    max_size=12,
)
small_sample = settings(max_examples=60, derandomize=True, database=None)


@small_sample
@given(expense_rows)
def test_expense_totals_reconcile_for_generated_ledger_rows(rows):
    expenses = [dict(id=str(index), category=category, kind=kind, amount_cents=amount)
                for index, (category, kind, amount) in enumerate(rows)]
    result = aggregate([day(expenses)])
    spending = sum(amount for _, kind, amount in rows if kind == "expense")
    refunds = sum(amount for _, kind, amount in rows if kind == "refund")
    assert result["expense_cents"] == spending
    assert result["refund_cents"] == refunds
    assert result["money_cents"] == spending - refunds
    assert sum(group["net_cents"] for group in result["expense_categories"].values()) == result["money_cents"]
    assert result["expense_record_count"] == len(rows)


@small_sample
@given(expense_rows, st.integers(min_value=0, max_value=12))
def test_split_days_and_meal_links_do_not_change_money(rows, split):
    expenses = [dict(id=str(index), category=category, kind=kind, amount_cents=amount)
                for index, (category, kind, amount) in enumerate(rows)]
    split = min(split, len(expenses))
    original = aggregate([day(expenses)])
    linked_meals = [dict(type="snack", expense_id=row["id"]) for row in expenses]
    transformed = aggregate([
        day(expenses[:split], linked_meals[:split], "2026-11-09"),
        day(expenses[split:], linked_meals[split:], "2026-11-10"),
    ])
    for key in ("expense_cents", "refund_cents", "money_cents", "expense_record_count", "expense_categories"):
        assert transformed[key] == original[key]
