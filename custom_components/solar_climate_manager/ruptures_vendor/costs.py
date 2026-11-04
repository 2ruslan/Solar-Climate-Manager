"""Restricted factory: this integration uses only upstream CostL1."""
from .costl1 import CostL1

def cost_factory(model, **params):
    if model != "l1":
        raise ValueError("Only l1 is bundled")
    return CostL1(**params)
