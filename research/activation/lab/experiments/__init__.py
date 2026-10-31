"""Experiment registry and default run order."""

from .activation import Activation
from .census import Census
from .consequence import Consequence
from .defense import Defense
from .effective_authority import EffectiveAuthority

REGISTRY = {c.name: c for c in (Census, Activation, Consequence, Defense, EffectiveAuthority)}

# Order matters: census + activation produce the data that defense and
# effective_authority read back.
ORDER = ["census", "activation", "consequence", "defense", "effective_authority"]
