from typing import List

from phi.tools.toolkit import Toolkit
from phi.utils.log import logger


class CalculatorTool(Toolkit):
    def __init__(self):
        super().__init__(name="calculator_tool")
        self.register(self.calculate)

    def calculate(self, args: List[str]) -> str:
        try:
            expression = " ".join(args)
            result = eval(expression)
            return str(result)
        except Exception as e:
            logger.error(f"Error in calculate: {e}")
            return "Error in calculation"
