"""booking_requirements: what to tell us to book a flight, as of today."""

from pathlib import Path

from contract import RequirementsInput, RequirementsOutput
from plugin import guide, receipts


def booking_requirements(value: RequirementsInput, workspace: Path) -> RequirementsOutput:
    return guide.build(value.topic, receipts.CLOCK()[:10])
