from typing import List
from card import Card, Deck, Suit, Rank
from player import Player
import random

class PokerGame:
    def __init__(self, player_names: List[str], starting_chips: int = 1000):
        self.players = [Player(name, starting_chips) for name in player_names]
        self.deck = Deck()
        self.community_cards: List[Card] = []
        self.pot = 0
        self.current_bet = 0
        self.dealer_index = 0
        self.small_blind = 10
        self.big_blind = 20
        self.current_player_index = 0
        self.game_state = "waiting"  # waiting, preflop, flop, turn, river, showdown
        self.last_raise = 0
        self.minimum_raise = self.big_blind

    def add_player(self, player_name: str) -> bool:
        """Add a new player to the game"""
        if len(self.players) >= 10:
            raise ValueError("Maximum number of players reached")
        if any(p.name == player_name for p in self.players):
            raise ValueError("Player name already taken")
        self.players.append(Player(player_name))
        return True

    def start_new_hand(self):
        # Reset game state
        self.deck.reset()
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.last_raise = 0
        self.minimum_raise = self.big_blind
        self.game_state = "preflop"
        
        # Reset players
        for player in self.players:
            player.reset_for_new_hand()

        # Deal cards
        for _ in range(2):  # Deal 2 cards to each player
            for player in self.players:
                card = self.deck.draw()
                player.receive_card(card)

        # Post blinds
        self._post_blinds()

    def _post_blinds(self):
        # Small blind
        sb_index = (self.dealer_index + 1) % len(self.players)
        self.players[sb_index].place_bet(self.small_blind)
        
        # Big blind
        bb_index = (self.dealer_index + 2) % len(self.players)
        self.players[bb_index].place_bet(self.big_blind)
        
        self.current_bet = self.big_blind
        self.pot = self.small_blind + self.big_blind
        self.current_player_index = (self.dealer_index + 3) % len(self.players)

    def deal_flop(self):
        if self.game_state != "preflop":
            return False
        
        # Burn a card
        self.deck.draw()
        # Deal 3 community cards
        for _ in range(3):
            card = self.deck.draw()
            card.face_up = True
            self.community_cards.append(card)
        
        self.game_state = "flop"
        self.current_bet = 0
        self.current_player_index = (self.dealer_index + 1) % len(self.players)
        return True

    def deal_turn(self):
        if self.game_state != "flop":
            return False
        
        # Burn a card
        self.deck.draw()
        # Deal 1 community card
        card = self.deck.draw()
        card.face_up = True
        self.community_cards.append(card)
        
        self.game_state = "turn"
        self.current_bet = 0
        self.current_player_index = (self.dealer_index + 1) % len(self.players)
        return True

    def deal_river(self):
        if self.game_state != "turn":
            return False
        
        # Burn a card
        self.deck.draw()
        # Deal 1 community card
        card = self.deck.draw()
        card.face_up = True
        self.community_cards.append(card)
        
        self.game_state = "river"
        self.current_bet = 0
        self.current_player_index = (self.dealer_index + 1) % len(self.players)
        return True

    def player_action(self, player_name: str, action_type: str, amount: int = 0) -> bool:
        player = next((p for p in self.players if p.name == player_name), None)
        if not player or not player.is_active:
            return False

        if player_name != self.players[self.current_player_index].name:
            return False

        if action_type == "bet":
            if amount < self.minimum_raise:
                return False
            if not player.place_bet(amount):
                return False
            self.current_bet = amount
            self.pot += amount
            self.last_raise = amount
            self.minimum_raise = amount * 2

        elif action_type == "fold":
            player.fold()
            if self._check_hand_end():
                return True

        elif action_type == "check":
            if self.current_bet > 0:
                return False

        self._next_player()
        return True

    def _next_player(self):
        while True:
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            if self.players[self.current_player_index].is_active:
                break

    def _check_hand_end(self) -> bool:
        active_players = [p for p in self.players if p.is_active]
        if len(active_players) == 1:
            self._end_hand(active_players[0])
            return True
        return False

    def _end_hand(self, winner: Player):
        winner.win_pot(self.pot)
        self.game_state = "waiting"
        self.dealer_index = (self.dealer_index + 1) % len(self.players)

    def get_game_state(self) -> dict:
        return {
            "game_state": self.game_state,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "community_cards": [str(card) for card in self.community_cards],
            "players": [{
                "name": p.name,
                "chips": p.chips,
                "current_bet": p.current_bet,
                "is_active": p.is_active,
                "hand": [str(card) for card in p.hand]
            } for p in self.players],
            "current_player": self.players[self.current_player_index].name
        }

    def collect_bets(self):
        for player in self.players:
            self.pot += player.current_bet
            player.current_bet = 0

    def get_active_players(self) -> List[Player]:
        return [p for p in self.players if p.is_active]

    def get_player_hands(self) -> str:
        result = []
        for player in self.players:
            if player.is_active:
                hand_str = " ".join(str(card) for card in player.hand)
                result.append(f"{player.name}: {hand_str}")
        return "\n".join(result)

    def get_community_cards(self) -> str:
        return " ".join(str(card) for card in self.community_cards)

    def __str__(self):
        return f"Pot: {self.pot}\nCommunity Cards: {self.get_community_cards()}\n\nPlayers:\n{self.get_player_hands()}" 