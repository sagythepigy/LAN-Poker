from typing import List
from card import Card

class Player:
    def __init__(self, name: str, chips: int = 1000):
        self.name = name
        self.chips = chips
        self.hand: List[Card] = []
        self.is_active = True
        self.current_bet = 0

    def receive_card(self, card: Card):
        self.hand.append(card)

    def clear_hand(self):
        self.hand = []
        self.current_bet = 0

    def place_bet(self, amount: int) -> bool:
        if amount > self.chips:
            return False
        self.chips -= amount
        self.current_bet += amount
        return True

    def win_pot(self, amount: int):
        self.chips += amount

    def fold(self):
        self.is_active = False

    def reset_for_new_hand(self):
        self.hand = []
        self.current_bet = 0
        self.is_active = True

    def __str__(self):
        return f"{self.name} (Chips: {self.chips})" 