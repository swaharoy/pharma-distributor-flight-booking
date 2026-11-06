"""The deterministic verifier: each tool's checks in its own module, and the booking task's verdict."""

from contract import Task, Tool

from . import booking, requirements, search, solve, trip

TOOLS = {
    Tool.BOOKING_REQUIREMENTS: requirements,
    Tool.GET_TRIP: trip,
    Tool.SEARCH_FLIGHTS: search,
    Tool.SOLVE_BOOKING: solve,
}


def _tool_output(module):
    """A tool task's check: its output judged as its one tool's verify_output judges it."""
    return lambda arguments, output, reference, workspace: module.verify_output(arguments, output, workspace)


# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {
    Task.BOOKING_REQUIREMENTS: _tool_output(requirements),
    Task.SEARCH_FLIGHTS: _tool_output(search),
    Task.BOOK_FLIGHT: booking.verify_task,
}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
