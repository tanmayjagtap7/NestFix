"""Housing budget math. Prices are monthly rent in dollars."""

from typing import Optional


CONTRIBUTION_TYPES = ("monthly_subsidy", "one_time_assistance", "percent_of_rent")


def default_bedrooms(family_size: int) -> int:
    size = family_size or 1
    if size <= 2:
        return 1
    if size <= 4:
        return 2
    return 3


def monthly_gross(annual_salary: float) -> float:
    return float(annual_salary or 0) / 12.0


def rule_of_thumb_budget(annual_salary: float, ratio: float = 0.30) -> float:
    return monthly_gross(annual_salary) * ratio


def percent_fraction(amount: float) -> float:
    value = float(amount or 0)
    if value <= 0:
        return 0.0
    if value <= 1:
        return value
    return value / 100.0


def employer_monthly_cover(
    price: Optional[float],
    contribution_type: str,
    contribution_amount: float,
    duration_months: Optional[int],
) -> float:
    if price is None:
        return 0.0
    rent = float(price)
    amount = float(contribution_amount or 0)
    if contribution_type == "monthly_subsidy":
        return min(rent, max(0.0, amount))
    if contribution_type == "percent_of_rent":
        return rent * percent_fraction(amount)
    if contribution_type == "one_time_assistance":
        months = duration_months or 12
        if months <= 0:
            months = 12
        return min(rent, max(0.0, amount) / float(months))
    return 0.0


def net_monthly_price(
    price: Optional[float],
    contribution_type: str,
    contribution_amount: float,
    duration_months: Optional[int],
) -> Optional[float]:
    if price is None:
        return None
    cover = employer_monthly_cover(price, contribution_type, contribution_amount, duration_months)
    return round(max(0.0, float(price) - cover), 2)


def estimated_cover_at_budget(
    housing_budget: float,
    contribution_type: str,
    contribution_amount: float,
    duration_months: Optional[int],
) -> float:
    """How many sticker-price dollars the employer adds on top of the 30% budget."""
    amount = float(contribution_amount or 0)
    if contribution_type == "monthly_subsidy":
        return max(0.0, amount)
    if contribution_type == "one_time_assistance":
        months = duration_months or 12
        if months <= 0:
            months = 12
        return max(0.0, amount) / float(months)
    if contribution_type == "percent_of_rent":
        fraction = percent_fraction(amount)
        if fraction >= 0.95:
            return housing_budget
        if fraction <= 0:
            return 0.0
        # budget is the net the employee can pay; sticker = net / (1 - fraction)
        return housing_budget * fraction / (1.0 - fraction)
    return 0.0


def sticker_search_cap(employee) -> float:
    budget = rule_of_thumb_budget(employee.annual_salary)
    extra = estimated_cover_at_budget(
        budget,
        employee.contribution_type,
        employee.contribution_amount,
        employee.contribution_duration_months,
    )
    return round(budget + extra, 2)


def contribution_label(employee) -> str:
    amount = float(employee.contribution_amount or 0)
    months = employee.contribution_duration_months
    kind = employee.contribution_type
    if kind == "monthly_subsidy":
        window = f" for {months} months" if months else ""
        return f"${amount:,.0f} monthly subsidy{window}"
    if kind == "percent_of_rent":
        shown = amount if amount > 1 else amount * 100
        return f"{shown:g}% of rent covered"
    if kind == "one_time_assistance":
        span = months or 12
        monthly = amount / span if span else amount
        return f"${amount:,.0f} one-time assistance, about ${monthly:,.0f}/mo over {span} months"
    return kind or "No contribution"


def money(value: Optional[float]) -> str:
    if value is None:
        return "an unlisted rent"
    return f"${value:,.0f}"
