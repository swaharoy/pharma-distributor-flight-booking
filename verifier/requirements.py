"""booking_requirements' checks: the answer is exactly what the contract and the airport table give for
the topic, as of the day it states."""

import dataclasses

from .checks import result
from .guide import build
from .rules import is_date


def verify_input(value):
    return result(True, f"topic {value.topic.value}")


def verify_output(input_value, output_value, workspace):
    if not is_date(output_value.today):
        return result(False, f"today {output_value.today!r} is not a real YYYY-MM-DD date")
    expected = build(input_value.topic, output_value.today)
    if dataclasses.asdict(output_value) != dataclasses.asdict(expected):
        return result(False, "the requirements differ from the booking task's contract and the airport list")
    return result(True, f"the {input_value.topic.value} requirements as of {output_value.today}")
