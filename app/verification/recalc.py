"""Re-evaluate a calculation record from its own inputs. A code check: no model is involved."""
import ast
import operator
from collections.abc import Callable
from decimal import Decimal

from app.domain.calculations import CalcRecord

TOLERANCE = Decimal("1e-9")  # the engine and this evaluator add in different orders; Decimal rounds at 28 digits
BINARY: dict[type, Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
}


def _eval(node: ast.AST, names: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval(node.body, names)
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        return BINARY[type(node.op)](_eval(node.left, names), _eval(node.right, names))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, names)
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return Decimal(node.value)
    raise ValueError("a formula may use only its input names, whole numbers, + - * / and brackets")


def evaluate(record: CalcRecord) -> Decimal:
    return _eval(ast.parse(record.formula, mode="eval"), {i.name: i.value for i in record.inputs})


def failures(records: list[CalcRecord]) -> list[str]:
    """Ids of records whose formula, run on their own inputs, does not give their result."""
    return [r.id for r in records if abs(evaluate(r) - r.result) > TOLERANCE]
