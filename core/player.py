"""Player dataclass — owns deck / hand / field / discard.

MVP: no gold spending, no XP, no saved decks. Just the four zones
and helpers to draw and play cards. GDD §5.1 / §7.1.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from core.card import Card
from data.settings_service import get_int


@dataclass
class Player:
    name: str = "Player"
    deck:     List[Card] = field(default_factory=list)
    hand:     List[Card] = field(default_factory=list)
    on_field: List[Card] = field(default_factory=list)
    discard:  List[Card] = field(default_factory=list)
    gold: int = 0
    kills: int = 0

    # ---- deck operations ----
    def draw_card(self) -> Optional[Card]:
        """Top-deck one card into hand. Returns the card, or None if deck is empty."""
        if not self.deck:
            return None
        card = self.deck.pop(0)
        self.hand.append(card)
        return card

    def draw_starting_hand(self, n: int) -> None:
        for _ in range(n):
            if self.draw_card() is None:
                break

    # ---- play / discard ----
    def play_card(self, card: Card) -> bool:
        """Move card from hand to field. Returns False if not allowed."""
        if card not in self.hand:
            return False
        if len(self.on_field) >= get_int("gameplay.field_limit"):
            return False
        self.hand.remove(card)
        self.on_field.append(card)
        return True

    def discard_from_hand(self, card: Card) -> bool:
        if card not in self.hand:
            return False
        self.hand.remove(card)
        card.graveyard_eligible = False
        self.discard.append(card)
        return True
