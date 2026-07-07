# Verification tests for mock calculator
from mock_calc_wrapper import Calculator

def test_calculator_add():
    c = Calculator()
    assert c.add(10, 5) == 15
