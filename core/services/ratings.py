import math

def elo_to_10(elo: float, midpoint: float = 1500.0, scale: float = 200.0) -> float:
    # logistic curve: midpoint maps to 5.00
    x = (elo - midpoint) / scale
    return 10.0 / (1.0 + math.exp(-x))

def elo_expected(r_a: float, r_b: float, scale: float = 400.0) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / scale))

def elo_update(winner: float, loser: float, k: float = 24.0, scale: float = 400.0):
    e_w = elo_expected(winner, loser, scale=scale)
    e_l = 1.0 - e_w
    return (
        winner + k * (1.0 - e_w),
        loser + k * (0.0 - e_l),
    )