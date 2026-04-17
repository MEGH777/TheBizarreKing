from .base import BaseAbility
from .the_world import TheWorld
from .king_crimson import KingCrimson

ABILITY_REGISTRY = {
    'The World': TheWorld,
    'King Crimson': KingCrimson,
}

def create_ability(name: str, color: str, state):
    if name in ABILITY_REGISTRY:
        return ABILITY_REGISTRY[name](color, state)
    return None

def get_available_abilities():
    return list(ABILITY_REGISTRY.keys())