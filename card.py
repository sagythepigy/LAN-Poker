from enum import Enum
import random

class Suit(Enum):
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"
    SPADES = "♠"

class Rank(Enum):
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"

class Card:
    def __init__(self, suit: Suit, rank: Rank):
        self.suit = suit
        self.rank = rank
        self.face_up = False

    def __str__(self):
        if not self.face_up:
            return "🂠"
        return f"{self.rank.value}{self.suit.value}"

    def flip(self):
        self.face_up = not self.face_up

class Deck:
    def __init__(self):
        self.cards = []
        self.reset()

    def reset(self):
        self.cards = [Card(suit, rank) 
                     for suit in Suit 
                     for rank in Rank]
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            raise ValueError("No cards left in deck")
        return self.cards.pop()

    def draw_multiple(self, count: int) -> list[Card]:
        return [self.draw() for _ in range(count)] 