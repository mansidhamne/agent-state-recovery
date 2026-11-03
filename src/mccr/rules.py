"""Domain rules, the single source of truth (doc section 6.5, invariant I2).

Imported only by tasks/gen_tasks.py. Agents never see this file.
"""
from __future__ import annotations

RECURRENCE_THRESHOLD = 2


def disposition(mel_category: str, in_stock: bool, conditions_met: bool) -> str:
    if mel_category == "NO_GO":
        return "HOLD"
    if in_stock:
        return "REPAIR_NOW"
    if mel_category in ("A", "B", "C") and conditions_met:
        return "DEFER_MEL"
    return "HOLD"


def reliability_review(failures_in_window: int) -> bool:
    return failures_in_window >= RECURRENCE_THRESHOLD


def dispatch_status(disposition_value: str, repair_complete: bool) -> str:
    if disposition_value == "DEFER_MEL":
        return "RELEASED"
    if disposition_value == "REPAIR_NOW" and repair_complete:
        return "RELEASED"
    return "HELD"


def parts_request(disposition_value: str, part_number: str) -> list[str]:
    return [part_number] if disposition_value in ("REPAIR_NOW", "DEFER_MEL") else []
