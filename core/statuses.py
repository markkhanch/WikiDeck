"""Central status glossary for WikiDeck effects."""

STATUSES = {
    "BLEEDING": "Damage this unit by 1 at the end of its turn. Stacks.",
    "VITALITY": "Boost this unit by 1 at the end of its turn. Stacks.",
    "ARMOR": "Absorbs damage. Does not count toward score.",
    "SHIELD": "Absorbs the next instance of damage.",
    "VEIL": "Cannot be targeted by abilities.",
    "IMMUNITY": "Cannot be targeted by anything.",
    "LOCK": "Disables this unit's ability.",
    "POISON": "At 2 stacks, destroy this unit.",
    "DOOMED": "Removed from the game when it leaves the battlefield.",
    "ZEAL": "Order ability can be used the same turn this card is played.",
}
