# Calculator wrapper class
import mock_math_core

class Calculator:
    def add(self, a, b):
        # Uses low-level raw_add helper
        return mock_math_core.raw_add(a, b)
        
    def subtract(self, a, b):
        return mock_math_core.raw_subtract(a, b)
