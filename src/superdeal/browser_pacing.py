"""Small randomized pause before each retailer browser navigation."""
from __future__ import annotations

import random
import time


def pause_before_navigation() -> None:
    """Pace every attempt, including the first and attempts after failures."""
    time.sleep(random.uniform(1.0, 2.0))
