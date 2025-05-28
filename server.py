from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import itertools
from collections import Counter
import time
import threading
import datetime
from poker_stats import PokerDatabase
import sqlite3
import socket

app = Flask(__name__)
app.config['SECRET_KEY'] = 'poker_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Store active games and their states
games = {}
player_rooms = {}  # Map player SIDs to their room IDs
player_names = {}  # Map player names to their current SIDs

# Initialize the database at the start of the server
try:
    stats_db = PokerDatabase(check_same_thread=False)
    stats_enabled = True
    print("Statistics tracking enabled")
except Exception as e:
    stats_db = None
    stats_enabled = False
    print(f"Statistics tracking disabled: {str(e)}")

# Near the top of the file where global variables are defined
game_stats = {}  # To store active game IDs and hand counters

# Function to format cards for database
def format_card_for_db(card):
    """Convert a Card object to a string format for database storage"""
    values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suits = ['Diamonds', 'Clubs', 'Hearts', 'Spades']
    try:
        # If card.value is an index for the values list
        if isinstance(card.value, int) and 0 <= card.value < len(values):
            card_value = values[card.value]
        else:
            card_value = str(card.value)
            
        # If card.suit is an index for the suits list
        if isinstance(card.suit, int) and 0 <= card.suit < len(suits):
            card_suit = suits[card.suit]
        else:
            card_suit = str(card.suit)
            
        return f"{card_value}-{card_suit}"
    except Exception as e:
        print(f"Error formatting card: {str(e)}")
        return "Unknown-Card"

# Add a safe way to record stats
def safe_record_stats(func, *args, **kwargs):
    """Safely call a stats_db method without crashing if stats are disabled"""
    if not stats_enabled or not stats_db:
        print(f"Stats tracking disabled - skipping call to {func.__name__}")
        return None
    try:
        # Print what function we're trying to call with what parameters
        func_name = func.__name__
        arg_str = ", ".join([str(a) for a in args])
        kwarg_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        params = ", ".join(filter(None, [arg_str, kwarg_str]))
        print(f"DB CALL: {func_name}({params})")
        
        # Ensure connection is open
        if not hasattr(stats_db, 'conn') or stats_db.conn is None:
            print("Reopening database connection")
            stats_db.conn = sqlite3.connect(stats_db.db_file, check_same_thread=stats_db.check_same_thread)
            
        # Call the function
        result = func(*args, **kwargs)
        
        # Log the result
        print(f"DB RESULT: {result}")
        return result
    except Exception as e:
        print(f"Error in statistics tracking when calling {func.__name__}: {str(e)}")
        # Print stack trace for debugging
        import traceback
        traceback.print_exc()
        return None

class Card:
    def __init__(self, value, suit):
        self.value = value  # 0-12 representing 2-A
        self.suit = suit    # 0-3 representing diamonds, clubs, hearts, spades
        self.showing = True

    def __repr__(self):
        values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['Diamonds', 'Clubs', 'Hearts', 'Spades']
        if self.showing:
            return f"{values[self.value]} of {suits[self.suit]}"
        return "[CARD]"
            
    def to_dict(self):
        if not self.showing:
            return {"hidden": True}
            
        values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['Diamonds', 'Clubs', 'Hearts', 'Spades']
        
        return {
            "value": values[self.value],
            "suit": suits[self.suit],
            "hidden": False,
            "showing": True
        }

class StandardDeck(list):
    def __init__(self):
        super().__init__()
        suits = list(range(4))
        values = list(range(13))
        [[self.append(Card(i, j)) for j in suits] for i in values]

    def shuffle(self):
        random.shuffle(self)

    def deal(self, location, times=1):
        for i in range(times):
            location.cards.append(self.pop(0))

    def burn(self):
        self.pop(0)

class PokerGame:
    def __init__(self, room_id, max_players=8):
        self.room_id = room_id
        self.max_players = max_players
        self.players = {}
        self.deck = None
        self.community_cards = []
        self.current_player_idx = 0
        self.dealer_idx = 0
        self.pot = 0
        self.current_bet = 0
        self.last_raise = 0
        self.game_state = "waiting"
        self.big_blind = 20
        self.small_blind = 10
        self.starting_chips = 10000
        self.highest_stake = 0
        self.fold_list = []
        self.all_in_players = []
        self.betting_round_complete = False
        self.last_aggressor = None
        self.min_raise = 0
        self.ante = 0  # Optional ante amount

    def start_new_round(self):
        """Start a new round with proper player cleanup and validation."""
        print("\n=== STARTING NEW ROUND ===")
        
        # CRITICAL: Ensure we have the room_id
        if not hasattr(self, 'room_id') or not self.room_id:
            print("ERROR: Game has no room_id!")
            return False
        
        room_id = self.room_id
        
        # First validate player connections
        for player_id in list(self.players.keys()):
            # Repair room mappings for players who are in the game
            if player_id not in player_rooms:
                print(f"Fixing missing room mapping for player {player_id}")
                player_rooms[player_id] = room_id
            elif player_rooms[player_id] != room_id:
                print(f"Correcting room mapping for player {player_id} from {player_rooms[player_id]} to {room_id}")
                player_rooms[player_id] = room_id
            
            # Check if they're actually connected - use player_rooms as the check instead
            # The socketio.server.manager.is_connected() method is causing issues
            if player_id not in player_rooms:
                print(f"Player {player_id} appears to be disconnected, removing from game")
                del self.players[player_id]
        
        # Check if we have enough players to start
        if len(self.players) < 2:
            print(f"Not enough players to start new round, only {len(self.players)} connected")
            self.game_state = "waiting"  # Set game to waiting state
            return False
        
        # Reset game state
        self.deck = StandardDeck()
        self.deck.shuffle()
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.last_raise = self.big_blind  # Initialize last raise to big blind
        self.min_raise = self.big_blind   # Initialize min raise to big blind
        self.betting_round_complete = False
        self.last_aggressor = None
        self.all_in_players = []
        self.fold_list = []
        self.game_state = "preflop"  # Set game state before dealing cards
        
        # Reset player states
        for player in self.players.values():
            player["hand"] = []
            player["current_bet"] = 0
            player["folded"] = False
            player["all_in"] = False
            player["is_winner"] = False
            player["score"] = None
        
        # Ensure dealer_idx is valid after player removal
        player_count = len(self.players)
        if player_count > 0 and (self.dealer_idx >= player_count or self.dealer_idx < 0):
            self.dealer_idx = 0
        
        # Collect antes if any
        if self.ante > 0:
            for player in self.players.values():
                ante_amount = min(self.ante, player["chips"])
                player["chips"] -= ante_amount
                player["current_bet"] = ante_amount
                self.pot += ante_amount
        
        # Deal hole cards
        self.deal_hole_cards()
        
        # Post blinds
        self.post_blinds()
        
        print(f"New round started with {len(self.players)} players")
        print(f"Dealer position: {self.dealer_idx}, Current player: {self.current_player_idx}")
        print("=== NEW ROUND STARTED ===\n")
        return True

    def deal_hole_cards(self):
        print("\n=== Dealing hole cards ===")
        # Reset all hands first
        for player in self.players.values():
            player["hand"] = []
        
        # Deal 2 cards to each active player
        for _ in range(2):
            for player_id in self.players:
                if not self.players[player_id]["folded"]:
                    card = self.deck.pop(0)
                    # Each player should see their own cards
                    card.showing = True
                    self.players[player_id]["hand"].append(card)
                    print(f"Dealt card to {self.players[player_id]['name']}: {card}")
        
        # Log the number of cards each player has
        for player_id, player in self.players.items():
            print(f"Player {player['name']} has {len(player['hand'])} cards.")
        
        # Broadcast the updated game state to each player individually
        for player_id in self.players:
            game_state = self.get_game_state(player_id)
            if hasattr(self, 'socketio'):
                print(f"Broadcasting initial hand to {self.players[player_id]['name']} (sid: {player_id})")
                self.socketio.emit('game_state', game_state, room=player_id)

    def deal_next_street(self):
        # CRITICAL: If game is finished or waiting for next round, do nothing
        if self.game_state in ["showdown", "round_complete", "waiting"]:
            print(f"Warning: deal_next_street called while in {self.game_state} state - ignoring")
            return
        
        print(f"Dealing next street. Current state: {self.game_state}")
        
        # Reset betting state for the new street
        self.current_bet = 0
        
        # When moving to a new street, the minimum raise resets to the big blind
        # This follows standard poker rules where each street's first raise must be at least the big blind
        self.min_raise = self.big_blind
        self.last_raise = self.big_blind
        
        print(f"NEW STREET: Reset current_bet=0, min_raise={self.big_blind} (big blind)")
        
        self.betting_round_complete = False
        self.last_aggressor = None
        
        # Reset each player's current bet for the new street
        for player in self.players.values():
            player["current_bet"] = 0
            
        # Determine the next state based on the current state
        intended_next_state = None
        if self.game_state == "preflop":
            intended_next_state = "flop"
        elif self.game_state == "flop":
            intended_next_state = "turn"
        elif self.game_state == "turn":
            intended_next_state = "river"
        # NOTE: 'river' state does NOT transition here; it goes to showdown via check_round_complete
        else:
            print(f"ERROR: deal_next_street called with unexpected state: {self.game_state}")
            return

        print(f"Dealing cards for {intended_next_state}")
        if intended_next_state == "flop":
            self.deck.burn()
            for _ in range(3):
                card = self.deck.pop(0)
                card.showing = True
                self.community_cards.append(card)
        elif intended_next_state == "turn":
            self.deck.burn()
            card = self.deck.pop(0)
            card.showing = True
            self.community_cards.append(card)
        elif intended_next_state == "river":
            self.deck.burn()
            card = self.deck.pop(0)
            card.showing = True
            self.community_cards.append(card)
        
        # Update game state *only* if it hasn't unexpectedly changed
        if self.game_state not in ["showdown", "round_complete", "waiting"]:
            print(f"*** UPDATING GAME STATE from {self.game_state} TO {intended_next_state} ***")
            self.game_state = intended_next_state

            # Set first player after dealer for post-flop rounds
            player_keys = list(self.players.keys())
            if len(player_keys) > 0:
                self.current_player_idx = (self.dealer_idx + 1) % len(player_keys)
                start_idx = self.current_player_idx
                skipped_count = 0
                while (self.players[player_keys[self.current_player_idx]]["folded"] or 
                       self.players[player_keys[self.current_player_idx]]["all_in"]):
                    self.current_player_idx = (self.current_player_idx + 1) % len(player_keys)
                    skipped_count += 1
                    if skipped_count > len(player_keys): # Prevent infinite loop
                        print("Error: Infinite loop detected in finding next player for deal_next_street.")
                        break 
                print(f"Next player set to index {self.current_player_idx}")
            else:
                print("Error: No players left to set next player.")
        else:
            print(f"Game state changed to {self.game_state} during card dealing, preventing state update to {intended_next_state}.")

    def handle_showdown(self):
        active_players = [p for p in self.players.values() if not p["folded"]]
        
        # First set the game state to showdown
        self.game_state = "showdown"
        
        # Record the hand in the database
        room_id = getattr(self, 'room_id', None)
        if room_id and room_id in game_stats and stats_enabled:
            game_stats[room_id]["hand_count"] += 1
            self.hand_number = game_stats[room_id]["hand_count"]
            
            try:
                # Convert community cards to string format for database
                card_strs = []
                for card in self.community_cards[:3] if len(self.community_cards) >= 3 else []:
                    card_strs.append(format_card_for_db(card))
                flop = ",".join(card_strs) if card_strs else None
                
                turn = None
                if len(self.community_cards) >= 4:
                    turn = format_card_for_db(self.community_cards[3])
                    
                river = None
                if len(self.community_cards) >= 5:
                    river = format_card_for_db(self.community_cards[4])
                
                # Record the hand with debug info
                print(f"Recording hand stats: Game ID={game_stats[room_id]['game_id']}, Hand #{self.hand_number}, Pot={self.pot}")
                hand_id = safe_record_stats(
                    stats_db.record_hand,
                    game_id=game_stats[room_id]["game_id"],
                    hand_number=self.hand_number,
                    pot_size=self.pot,
                    flop=flop,
                    turn=turn,
                    river=river
                )
                
                if hand_id:
                    game_stats[room_id]["current_hand_id"] = hand_id
                    print(f"Hand recorded with ID: {hand_id}")
                else:
                    print("Failed to record hand ID")
                
                # Store starting chips for each player
                for player_id, player in self.players.items():
                    player["starting_chips"] = player["chips"]
            except Exception as e:
                print(f"Error recording hand: {str(e)}")
        
        # If only one player remains, they win
        if len(active_players) == 1:
            winner = active_players[0]
            winner["chips"] += self.pot
            winner["is_winner"] = True
            
            # Reveal winner's cards
            for card in winner["hand"]:
                card.showing = True
            
            # Record player hands in the database
            if stats_enabled and room_id and room_id in game_stats and "current_hand_id" in game_stats[room_id]:
                try:
                    # Create a mapping of player_sid to player_id once
                    player_id_map = {}
                    for player_sid, player in self.players.items():
                        if player_sid in player_names:
                            player_name = player_names[player_sid]
                            try:
                                # Get player ID directly using add_player, which returns existing ID if player exists
                                player_id = safe_record_stats(stats_db.add_player, player_name)
                                if player_id:
                                    player_id_map[player_sid] = player_id
                            except Exception as e:
                                print(f"Error getting player ID for {player_name}: {str(e)}")
                    
                    # Now record each player's hand
                    for player_sid, player in self.players.items():
                        if player_sid not in player_id_map:
                            print(f"Warning: No player_id found for {player_sid}, skipping hand recording")
                            continue
                            
                        player_id = player_id_map[player_sid]
                        
                        # Format cards for database using the format_card_for_db function
                        cards_str = ",".join([format_card_for_db(card) for card in player["hand"]])
                        
                        # Get hand type description
                        hand_type = "Fold" if player["folded"] else self.get_hand_type(player)
                        
                        # Record player hand with clear parameters
                        print(f"Recording player hand: {player_names[player_sid]}, Cards: {cards_str}, Winner: {player['is_winner']}")
                        safe_record_stats(
                            stats_db.record_player_hand,
                            hand_id=game_stats[room_id]["current_hand_id"],
                            player_id=player_id,
                            starting_chips=player.get("starting_chips", player["chips"]),
                            ending_chips=player["chips"],
                            cards=cards_str,
                            position=list(self.players.keys()).index(player_sid),
                            is_winner=player["is_winner"],
                            final_hand_type=hand_type
                        )
                except Exception as e:
                    print(f"Error recording player hands: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            # Broadcast showdown state immediately
            self.broadcast_game_state()
            
            # Mark the game as waiting for next round start (temporarily)
            self.game_state = "round_complete"
            print("*** GAME STATE CHANGED TO ROUND_COMPLETE - STARTING TIMER FOR NEW ROUND ***")
            
            # Broadcast the round_complete state so clients can display winner
            self.broadcast_game_state() 

            # Start timer for the next round
            timer = threading.Timer(5.0, self._start_new_round_safely) # Use a wrapper for safety
            timer.daemon = True
            timer.start()
            print("Timer started for new round (5 seconds)")
            
            return True, "Showdown complete"
        
        # Reveal all hands for showdown
        for player in active_players:
            for card in player["hand"]:
                card.showing = True
        
        # Evaluate hands for all active players
        for player in active_players:
            player["score"] = self.evaluate_hand(player["hand"], self.community_cards)
            
        # Find winner(s)
        best_score = max(player["score"] for player in active_players)
        winners = [p for p in active_players if p["score"] == best_score]
        
        # Split pot among winners
        win_amount = self.pot // len(winners)
        for winner in winners:
            winner["chips"] += win_amount
            winner["is_winner"] = True
        
        # Record player hands in the database
        if stats_enabled and room_id and room_id in game_stats and "current_hand_id" in game_stats[room_id]:
            try:
                # Create a mapping of player_sid to player_id once
                player_id_map = {}
                for player_sid, player in self.players.items():
                    if player_sid in player_names:
                        player_name = player_names[player_sid]
                        try:
                            # Get player ID directly using add_player, which returns existing ID if player exists
                            player_id = safe_record_stats(stats_db.add_player, player_name)
                            if player_id:
                                player_id_map[player_sid] = player_id
                        except Exception as e:
                            print(f"Error getting player ID for {player_name}: {str(e)}")
                
                # Now record each player's hand
                for player_sid, player in self.players.items():
                    if player_sid not in player_id_map:
                        print(f"Warning: No player_id found for {player_sid}, skipping hand recording")
                        continue
                        
                    player_id = player_id_map[player_sid]
                    
                    # Format cards for database using the format_card_for_db function
                    cards_str = ",".join([format_card_for_db(card) for card in player["hand"]])
                    
                    # Get hand type description
                    hand_type = "Fold" if player["folded"] else self.get_hand_type(player)
                    
                    # Record player hand with clear parameters
                    print(f"Recording player hand: {player_names[player_sid]}, Cards: {cards_str}, Winner: {player['is_winner']}")
                    safe_record_stats(
                        stats_db.record_player_hand,
                        hand_id=game_stats[room_id]["current_hand_id"],
                        player_id=player_id,
                        starting_chips=player.get("starting_chips", player["chips"]),
                        ending_chips=player["chips"],
                        cards=cards_str,
                        position=list(self.players.keys()).index(player_sid),
                        is_winner=player["is_winner"],
                        final_hand_type=hand_type
                    )
            except Exception as e:
                print(f"Error recording player hands: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Broadcast showdown state immediately
        self.broadcast_game_state()
        
        # Mark the game as waiting for next round start (temporarily)
        self.game_state = "round_complete"
        print("*** GAME STATE CHANGED TO ROUND_COMPLETE - STARTING TIMER FOR NEW ROUND ***")
        
        # Broadcast the round_complete state again to ensure clients see the winner info
        self.broadcast_game_state()

        # Start timer for the next round
        timer = threading.Timer(5.0, self._start_new_round_safely) # Use a wrapper for safety
        timer.daemon = True
        timer.start()
        print("Timer started for new round (5 seconds)")
        
        return True, "Showdown complete"

    def _start_new_round(self):
        """Internal method called by the timer to start a new round."""
        print("Timer fired - starting new round")
        if len(self.players) < 2:
            print("Not enough players to start new round")
            return False
        
        try:
            # Reset game state
            self.game_state = "preflop"
            self.deck = StandardDeck()
            self.deck.shuffle()
            self.community_cards = []
            self.pot = 0
            self.current_bet = 0
            self.last_raise = 0
            self.betting_round_complete = False
            self.last_aggressor = None
            self.all_in_players = []
            self.fold_list = []
            self.min_raise = self.big_blind
            
            # Reset player states
            for player in self.players.values():
                player["hand"] = []
                player["current_bet"] = 0
                player["folded"] = False
                player["all_in"] = False
                player["is_winner"] = False
                player["score"] = None
            
            # Move dealer button and set first player
            self.dealer_idx = (self.dealer_idx + 1) % len(self.players)
            
            # Deal new hands and post blinds
            self.deal_hole_cards()
            self.post_blinds()
            
            # Broadcast the new game state
            print("Broadcasting new game state after round start")
            self.broadcast_game_state()
            return True
        except Exception as e:
            print(f"Error starting new round: {str(e)}")
            # Force restart new round after a delay
            timer = threading.Timer(2.0, self.start_new_round)
            timer.daemon = True
            timer.start()
            return False

    def broadcast_game_state(self):
        """Broadcast the current game state to all players."""
        if not hasattr(self, 'socketio'):
            return
        
        # Ensure room_id is set
        if not hasattr(self, 'room_id') or not self.room_id:
            print("ERROR: Cannot broadcast - game has no room_id!")
            return
        
        room_id = self.room_id
        
        # Validate player connections before broadcasting
        print(f"Validating player connections before broadcast")
        for player_id in list(self.players.keys()):
            if player_id not in player_rooms:
                print(f"Fixing player {player_id} room mapping to {room_id}")
                player_rooms[player_id] = room_id
        
        # Log all active players before broadcasting
        print(f"Broadcasting game state to players: {list(self.players.keys())}")
        active_players = []
        
        # Check which players are actually still connected to the socket
        connected_players = [sid for sid in self.players.keys() 
                             if sid in player_rooms]
        
        for player_sid in list(self.players.keys()):
            try:
                # Check if socket is actually connected, not just in player_rooms
                if player_sid not in connected_players:
                    print(f"Warning: Player {player_sid} socket not connected - skipping broadcast")
                    continue
                    
                active_players.append(player_sid)
                game_state = self.get_game_state(player_sid)
                self.socketio.emit('game_state', game_state, room=player_sid)
            except Exception as e:
                print(f"Error broadcasting to {player_sid}: {str(e)}")
        
        print(f"Successfully broadcast to {len(active_players)} players: {active_players}")

    def get_game_state(self, for_player_sid=None):
        print(f"\n=== Generating game state for {for_player_sid} ===")
        state = {
            "pot": self.pot,
            "community_cards": [card.to_dict() for card in self.community_cards],
            "current_bet": self.current_bet,
            "game_state": self.game_state,
            "current_player": list(self.players.keys())[self.current_player_idx] if self.game_state != "waiting" else None,
            "max_players": self.max_players,
            "big_blind": self.big_blind,
            "last_raise": self.last_raise,
            "min_raise": self.min_raise,
            "players": {}
        }
        
        print(f"Game state: {self.game_state}")
        print(f"Number of players: {len(self.players)}")
        print(f"Players in game: {[p['name'] for p in self.players.values()]}")
        
        for sid, player in self.players.items():
            player_state = {
                "name": player["name"],
                "chips": player["chips"],
                "current_bet": player["current_bet"],
                "folded": player["folded"],
                "all_in": player["all_in"],
                "is_winner": player.get("is_winner", False),
                "score": player.get("score", None)
            }
            
            print(f"\nProcessing player {player['name']} (sid: {sid})")
            print(f"Has {len(player['hand'])} cards in hand")
            print(f"Should show cards: {sid == for_player_sid or self.game_state == 'showdown'}")
            
            # Always include hand array, even if empty
            player_state["hand"] = []
            
            if player["hand"]:
                if sid == for_player_sid or self.game_state == "showdown":
                    print(f"Showing cards to {player['name']}")
                    player_state["hand"] = [card.to_dict() for card in player["hand"]]
                    # Debug print the actual cards
                    for card in player["hand"]:
                        print(f"Card: {card}")
                else:
                    print(f"Hiding cards from {player['name']}")
                    player_state["hand"] = [{"hidden": True} for _ in player["hand"]]
            
            state["players"][sid] = player_state
        
        return state

    def add_player(self, player_id, name):
        if len(self.players) >= self.max_players:
            return False
        self.players[player_id] = {
            'name': name,
            'chips': self.starting_chips,  # Use the starting_chips value
            'hand': [],
            'current_bet': 0,
            'folded': False,
            'all_in': False
        }
        return True

    def start_game(self):
        if len(self.players) < 2:
            return False
            
        self.deck = StandardDeck()
        self.deck.shuffle()
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.last_raise = 0
        self.game_state = "preflop"
        
        # Deal cards to players
        self.deal_hole_cards()
        # Post blinds
        self.post_blinds()
        return True

    def deal_flop(self):
        self.deck.pop(0)  # Burn card
        for _ in range(3):
            self.community_cards.append(self.deck.pop(0))
        self.game_state = "flop"
        self.current_bet = 0
        for player in self.players.values():
            player["current_bet"] = 0

    def deal_turn(self):
        self.deck.pop(0)  # Burn card
        self.community_cards.append(self.deck.pop(0))
        self.game_state = "turn"
        self.current_bet = 0
        for player in self.players.values():
            player["current_bet"] = 0

    def deal_river(self):
        self.deck.pop(0)  # Burn card
        self.community_cards.append(self.deck.pop(0))
        self.game_state = "river"
        self.current_bet = 0
        for player in self.players.values():
            player["current_bet"] = 0

    def post_blinds(self):
        player_sids = list(self.players.keys())
        
        if len(player_sids) < 2:
            print("Not enough players to post blinds")
            return False
        
        # For heads-up play (2 players), button is SB and other player is BB
        if len(player_sids) == 2:
            sb_pos = self.dealer_idx  # Button is small blind
            bb_pos = (self.dealer_idx + 1) % 2  # Other player is big blind
        else:
            # Small blind position is left of dealer
            sb_pos = (self.dealer_idx + 1) % len(player_sids)
            bb_pos = (self.dealer_idx + 2) % len(player_sids)
        
        print(f"Dealer position: {self.dealer_idx}, SB position: {sb_pos}, BB position: {bb_pos}")
        
        # Small blind
        sb_player = self.players[player_sids[sb_pos]]
        sb_amount = min(self.small_blind, sb_player["chips"])
        sb_player["chips"] -= sb_amount
        sb_player["current_bet"] = sb_amount
        self.pot += sb_amount
        
        # Big blind
        bb_player = self.players[player_sids[bb_pos]]
        bb_amount = min(self.big_blind, bb_player["chips"])
        bb_player["chips"] -= bb_amount
        bb_player["current_bet"] = bb_amount
        self.pot += bb_amount
        
        # Set current bet to big blind amount
        self.current_bet = bb_amount
        
        # Initialize minimum raise to the big blind at the start of the hand
        # In poker, the first raise must be at least the size of the big blind
        self.min_raise = self.big_blind
        self.last_raise = self.big_blind
        
        print(f"BLINDS POSTED: SB={sb_amount}, BB={bb_amount}, Current bet={self.current_bet}")
        print(f"Minimum raise set to {self.min_raise} (big blind)")
        
        # First to act in preflop is UTG (left of BB)
        if len(player_sids) == 2:
            # In heads-up, SB acts first preflop
            self.current_player_idx = sb_pos
        else:
            # For 3+ players, UTG acts first preflop
            self.current_player_idx = (bb_pos + 1) % len(player_sids)
        
        print(f"First to act: {self.current_player_idx} - {player_sids[self.current_player_idx]}")
        self.last_aggressor = bb_pos  # BB is the last aggressor preflop
        
        return True

    def handle_player_action(self, player_id, action, amount=None):
        print(f"Player action: {player_id} performing {action} with amount {amount}")
        print(f"Current game state: {self.game_state}")
        
        # Prevent actions during round_complete state - this ensures the only valid action
        # is starting a new round via the start_new_round handler
        if self.game_state == "round_complete":
            print(f"Ignoring action {action} - game is in round_complete state")
            return False, "Game is waiting for winner to start new round"
        
        if self.game_state == "waiting" or self.game_state == "showdown":
            return False, "Game is not in progress"
        
        if player_id != list(self.players.keys())[self.current_player_idx]:
            return False, "Not your turn"
        
        player = self.players[player_id]
        
        if player["folded"] or player["all_in"]:
            return False, "Cannot act - player has folded or is all-in"

        # Calculate stake gap (how much more the player needs to call)
        stake_gap = self.current_bet - player["current_bet"]
        
        # Perform action
        success, message = self._perform_action(player_id, action, amount, stake_gap)
        
        # If action was successful, check if the round needs to end
        if success:
            # CRITICAL: Call check_round_complete only after action is fully processed
            self.check_round_complete()
        
        return success, message

    # Separate the action logic from the next_player/check_round logic
    def _perform_action(self, player_id, action, amount, stake_gap):
        player = self.players[player_id]
        
        if action == "check":
            if stake_gap > 0:
                return False, "Cannot check - there is an active bet, must call or fold"
            if self.game_state == "preflop" and player["current_bet"] < self.big_blind:
                return False, "Cannot check - must at least call the big blind"
            self.next_player()
            return True, "Player checked"
            
        elif action == "fold":
            player["folded"] = True
            self.fold_list.append(player_id)
            self.next_player()
            return True, "Player folded"
            
        elif action == "call":
            if stake_gap <= 0:
                return False, "No bet to call - you can check instead"
            
            # Determine correct call amount
            call_amount = stake_gap
            
            # Handle all-in case
            if call_amount > player["chips"]:
                call_amount = player["chips"]
                player["all_in"] = True
                self.all_in_players.append(player_id)
            
            # Process the call
            player["chips"] -= call_amount
            player["current_bet"] += call_amount
            self.pot += call_amount
            
            print(f"CALL: Player called {call_amount} to match current bet of {self.current_bet}")
            
            self.next_player()
            return True, "Player called"
            
        elif action == "raise":
            if not amount:
                return False, "Must specify raise amount"
            total_amount = int(amount)
            
            # Calculate how much the player is raising by
            raise_amount = total_amount - player["current_bet"]
            
            # Calculate the actual raise increment (how much more than the current bet)
            raise_increment = total_amount - self.current_bet
            
            # Validate minimum raise amount based on poker rules
            # If no previous raise on this street, min raise is the big blind
            # Otherwise, it's the amount of the previous raise
            min_raise_size = self.min_raise
            min_raise_to = self.current_bet + min_raise_size
            
            print(f"RAISE ATTEMPT: Current bet: {self.current_bet}, Min raise size: {min_raise_size}")
            print(f"Player attempting to raise from {player['current_bet']} to {total_amount} (minimum total: {min_raise_to})")
            
            # Validate raise amount
            if total_amount <= self.current_bet:
                return False, f"Raise must be greater than current bet of {self.current_bet}"
                
            if total_amount < min_raise_to:
                return False, f"Minimum raise is to {min_raise_to} (current bet {self.current_bet} + minimum raise {min_raise_size})"
                
            if total_amount > player["chips"] + player["current_bet"]:
                return False, "Not enough chips"
            
            # Process the raise
            player["chips"] -= raise_amount
            player["current_bet"] = total_amount
            self.pot += raise_amount
            
            # The amount raised OVER the current bet becomes the new minimum raise for this street
            previous_bet = self.current_bet
            self.current_bet = total_amount
            self.last_raise = raise_increment
            self.min_raise = raise_increment
            
            print(f"RAISE SUCCESSFUL: New bet {self.current_bet} (raised {raise_increment} over previous bet of {previous_bet})")
            print(f"New minimum raise is now {self.min_raise}")
            
            self.last_aggressor = self.current_player_idx
            self.betting_round_complete = False  # Reset betting round completion
            
            if player["chips"] == 0:
                player["all_in"] = True
                self.all_in_players.append(player_id)
                
            self.next_player()
            return True, f"Player raised to {total_amount}"
            
        elif action == "all_in":
            all_in_amount = player["chips"]
            if all_in_amount == 0:
                return False, "No chips to go all-in with"
            
            player["chips"] = 0
            player["all_in"] = True
            self.all_in_players.append(player_id)
            self.pot += all_in_amount
            old_bet = player["current_bet"]
            player["current_bet"] += all_in_amount
            
            if player["current_bet"] > self.current_bet:
                self.last_raise = player["current_bet"] - self.current_bet # Amount of raise
                self.current_bet = player["current_bet"] # Update current bet level
                self.min_raise = self.last_raise
                self.last_aggressor = self.current_player_idx
                self.betting_round_complete = False  # Reset betting round completion
            self.next_player()
            return True, "Player is all-in"

        return False, "Invalid action"

    def determine_winner(self):
        active_players = [p for p in self.players.values() if not p["folded"]]
        
        if len(active_players) == 1:
            self.winner = active_players[0]
            self.winner["chips"] += self.pot
            return
            
        # Calculate hand scores for all active players
        player_scores = []
        for player in active_players:
            score, hand = self.evaluate_hand(player["hand"], self.community_cards)
            player_scores.append((score, player))
            
        # Sort by score (highest first)
        player_scores.sort(reverse=True)
        
        # Handle ties
        winning_score = player_scores[0][0]
        winners = [p for s, p in player_scores if s == winning_score]
        
        # Split pot among winners
        split_amount = self.pot // len(winners)
        for winner in winners:
            winner["chips"] += split_amount
            
        # Set the winner (for display purposes, just use the first one)
        self.winner = winners[0]

    def handle_action(self, sid, action, amount=0):
        if sid not in self.players:
            return False, "Player not in game"
            
        if list(self.players.keys())[self.current_player_idx] != sid:
            return False, "Not your turn"
            
        player = self.players[sid]
        if player["folded"]:
            return False, "Player has folded"
            
        player_idx = list(self.players.keys()).index(sid)

        # Validate action based on game state and current bet
        if action == "check":
            if self.current_bet > player["current_bet"]:
                return False, "Cannot check, must call or fold"
            if self.game_state == "preflop" and player["current_bet"] < self.big_blind:
                return False, "Cannot check during preflop without calling big blind"
                
        if action == "call":
            call_amount = self.current_bet - player["current_bet"]
            if call_amount == 0:
                return False, "No bet to call, you can check"
            if call_amount > player["chips"]:
                return False, "Not enough chips, you can go all-in"
                
        if action == "raise":
            min_raise = max(self.big_blind, self.current_bet + self.last_raise)
            if amount < min_raise:
                return False, f"Minimum raise is {min_raise}"
            if amount > player["chips"] + player["current_bet"]:
                return False, "Not enough chips"
            if amount <= self.current_bet:
                return False, "Raise must be greater than current bet"

        # Handle the action
        if action == "fold":
            player["folded"] = True
            self.next_player()
            return True, "Player folded"
            
        elif action == "check":
            self.next_player()
            return True, "Player checked"
            
        elif action == "call":
            call_amount = self.current_bet - player["current_bet"]
            if call_amount > player["chips"]:
                # Player must go all-in
                call_amount = player["chips"]
                player["all_in"] = True
                self.all_in_players.append(player)
            player["chips"] -= call_amount
            player["current_bet"] += call_amount
            self.pot += call_amount
            self.next_player()
            return True, "Player called"
            
        elif action == "raise":
            total_amount = amount
            raise_amount = total_amount - player["current_bet"]
            if raise_amount > player["chips"]:
                return False, "Not enough chips"
            player["chips"] -= raise_amount
            player["current_bet"] = total_amount
            self.pot += raise_amount
            self.current_bet = total_amount
            self.last_raise = total_amount - self.current_bet
            self.last_aggressor = player_idx
            self.next_player()
            return True, "Player raised"
            
        elif action == "all_in":
            all_in_amount = player["chips"]
            if all_in_amount == 0:
                return False, "No chips to go all-in with"
                
            player["chips"] = 0
            player["all_in"] = True
            self.all_in_players.append(player)
            self.pot += all_in_amount
            old_bet = player["current_bet"]
            player["current_bet"] += all_in_amount
            
            # If all-in amount is higher than current bet, it counts as a raise
            if player["current_bet"] > self.current_bet:
                self.current_bet = player["current_bet"]
                self.last_raise = player["current_bet"] - old_bet
                self.last_aggressor = player_idx
                
            self.next_player()
            return True, "Player is all-in"

        return False, "Invalid action"

    def next_player(self):
        active_players = [p for p in self.players.values() if not p["folded"] and not p["all_in"]]
        if len(active_players) <= 1:
            self.betting_round_complete = True
            return

        initial_idx = self.current_player_idx
        while True:
            self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
            current_player = self.players[list(self.players.keys())[self.current_player_idx]]
            
            # Skip folded or all-in players
            if not current_player["folded"] and not current_player["all_in"]:
                # If we've reached the last aggressor and everyone has matched the bet, round is complete
                if (self.current_player_idx == self.last_aggressor and 
                    all(p["current_bet"] == self.current_bet or p["folded"] or p["all_in"] 
                        for p in self.players.values())):
                    self.betting_round_complete = True
                    break
                
            # If we've gone full circle and everyone has matched or folded
            if self.current_player_idx == initial_idx:
                if all(p["current_bet"] == self.current_bet or p["folded"] or p["all_in"] 
                      for p in self.players.values()):
                    self.betting_round_complete = True
                break
            
            # If we've found a valid next player, break
            if not current_player["folded"] and not current_player["all_in"]:
                break

    def check_round_complete(self):
        print(f"Checking if round is complete. Current state: {self.game_state}")
        
        # CRITICAL: If game is already finished or waiting for next round, do nothing
        if self.game_state in ["showdown", "round_complete", "waiting"]:
            print(f"Game state is {self.game_state}, check_round_complete taking no action.")
            return False # Return False as no state change occurred here
        
        active_players = [p for p in self.players.values() if not p["folded"]]
        
        # If only one player remains, they win
        if len(active_players) == 1:
            print(f"Only one active player remains - *** INTENDING TO GO TO SHOWDOWN ***")
            self.game_state = "showdown" # Set state first
            self.handle_showdown()      # Then handle it (which will set to round_complete)
            return True
        
        # Check if betting round is complete
        if self.betting_round_complete:
            print(f"Betting round complete - current game state: {self.game_state}")
            if self.game_state == "river":
                print(f"River complete - *** INTENDING TO GO TO SHOWDOWN ***")
                self.game_state = "showdown" # Set state first
                self.handle_showdown()      # Then handle it
            else:
                # Double check state before dealing next street
                if self.game_state not in ["showdown", "round_complete", "waiting"]:
                    print(f"Moving to next street from {self.game_state}")
                    self.deal_next_street()
                else:
                    print(f"State is {self.game_state}, preventing deal_next_street call from check_round_complete.")
            return True
        
        print("Betting round not complete.")
        return False

    def evaluate_hand(self, hole_cards, community_cards):
        all_cards = hole_cards + community_cards
        all_combinations = list(itertools.combinations(all_cards, 5))
        best_score = [0] * 8  # Initialize with lowest possible score

        for combo in all_combinations:
            score = self.score_hand(list(combo))
            if score > best_score:
                best_score = score

        return best_score

    def score_hand(self, cards):
        values = sorted([c.value for c in cards])
        suits = [c.suit for c in cards]
        
        # Check for straight and flush
        is_flush = len(set(suits)) == 1
        is_straight = (values == list(range(min(values), max(values) + 1)) or 
                      values == [0, 1, 2, 3, 12])  # Ace-low straight
        
        # Count frequencies of values
        value_counts = Counter(values)
        freq_counts = sorted(value_counts.values(), reverse=True)
        
        # Calculate base score
        if is_straight and is_flush:
            if values == [8, 9, 10, 11, 12]:  # Royal flush
                return [9, 12]
            return [8, max(values)]  # Straight flush
            
        if freq_counts[0] == 4:  # Four of a kind
            value = [v for v, count in value_counts.items() if count == 4][0]
            kicker = [v for v, count in value_counts.items() if count == 1][0]
            return [7, value, kicker]
            
        if freq_counts == [3, 2]:  # Full house
            three_kind = [v for v, count in value_counts.items() if count == 3][0]
            pair = [v for v, count in value_counts.items() if count == 2][0]
            return [6, three_kind, pair]
            
        if is_flush:
            return [5] + sorted(values, reverse=True)
            
        if is_straight:
            if values == [0, 1, 2, 3, 12]:  # Ace-low straight
                return [4, 3]
            return [4, max(values)]
            
        if freq_counts[0] == 3:  # Three of a kind
            value = [v for v, count in value_counts.items() if count == 3][0]
            kickers = sorted([v for v, count in value_counts.items() if count == 1], reverse=True)
            return [3, value] + kickers
            
        if freq_counts[:2] == [2, 2]:  # Two pair
            pairs = sorted([v for v, count in value_counts.items() if count == 2], reverse=True)
            kicker = [v for v, count in value_counts.items() if count == 1][0]
            return [2] + pairs + [kicker]
            
        if freq_counts[0] == 2:  # One pair
            pair = [v for v, count in value_counts.items() if count == 2][0]
            kickers = sorted([v for v, count in value_counts.items() if count == 1], reverse=True)
            return [1, pair] + kickers
            
        return [0] + sorted(values, reverse=True)  # High card

    def remove_player(self, player_id):
        """Remove a player from the game."""
        if player_id in self.players:
            del self.players[player_id]
            # If we're in the middle of a round, adjust indices
            if self.game_state != "waiting":
                # Get list of remaining players
                player_list = list(self.players.keys())
                if len(player_list) > 0:
                    # Adjust dealer position
                    if self.dealer_idx >= len(player_list):
                        self.dealer_idx = 0
                    # Adjust current player position
                    if self.current_player_idx >= len(player_list):
                        self.current_player_idx = 0
                    
                    # If only one player remains, they win the pot
                    if len(player_list) == 1:
                        winner = self.players[player_list[0]]
                        winner["chips"] += self.pot
                        winner["is_winner"] = True
                        self.game_state = "showdown"
                        self.broadcast_game_state()
                        # Start new round after delay
                        def start_next_round():
                            time.sleep(3)
                            self.start_new_round()
                        thread = threading.Thread(target=start_next_round)
                        thread.daemon = True
                        thread.start()

    def get_hand_type(self, player):
        """Get a text description of the hand type based on score."""
        if not player or "score" not in player or not player["score"]:
            return "Unknown"
        
        score = player["score"]
        if not score:
            return "Unknown"
        
        hand_type_map = {
            9: "Straight Flush",
            8: "Four of a Kind",
            7: "Full House",
            6: "Flush",
            5: "Straight",
            4: "Three of a Kind",
            3: "Two Pair",
            2: "One Pair",
            1: "High Card"
        }
        
        return hand_type_map.get(score[0], "Unknown")

    def _start_new_round_safely(self):
        """Wrapper to safely start a new round from a timer thread."""
        print("Timer callback triggered - attempting to start new round")
        try:
            success = self.start_new_round()
            if success:
                # Broadcast the new game state after successfully starting
                print("Broadcasting game state after automatic round start")
                self.broadcast_game_state()
            else:
                print("Failed to start new round automatically (e.g., not enough players)")
                # If failed (e.g., not enough players), broadcast the waiting state
                self.broadcast_game_state() 
        except Exception as e:
            print(f"Error in timer callback _start_new_round_safely: {str(e)}")
            # Potentially try again or log the error more formally

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/game/<room_id>')
def game(room_id):
    return render_template('game.html', room_id=room_id)

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('create_room')
def handle_create_room(data):
    room_id = data['room_id']
    player_name = data['player_name']
    max_players = int(data.get('max_players', 10))  # Default to 10 if not specified
    
    if room_id in games:
        emit('error', {'message': 'Room already exists'})
        return
        
    # Create new game with max players limit and pass socketio reference
    games[room_id] = PokerGame(room_id, max_players)
    games[room_id].socketio = socketio  # Important: pass socketio reference
    
    # Record the game start in the database
    try:
        game_id = safe_record_stats(stats_db.record_game_start, num_players=1, big_blind=games[room_id].big_blind)
        game_stats[room_id] = {"game_id": game_id, "hand_count": 0}
        
        # Record player in the database
        player_id = safe_record_stats(stats_db.add_player, player_name)
        print(f"Added player {player_name} with ID {player_id} to database")
    except Exception as e:
        print(f"Error recording game/player in database: {str(e)}")
        # Continue without statistics tracking if there's an error
    
    try:
        games[room_id].add_player(request.sid, player_name)
    except ValueError as e:
        emit('error', {'message': str(e)})
        return
        
    player_rooms[request.sid] = room_id
    player_names[request.sid] = player_name
    
    join_room(room_id)
    emit('room_created', {'room_id': room_id, 'player_name': player_name})

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data['room_id']
    player_name = data['player_name']
    
    if room_id not in games:
        emit('error', {'message': 'Room does not exist'})
        return
        
    game = games[room_id]
    
    try:
        game.add_player(request.sid, player_name)
    except ValueError as e:
        emit('error', {'message': str(e)})
        return
    
    # Record player in the database
    try:
        player_id = safe_record_stats(stats_db.add_player, player_name)
        print(f"Added player {player_name} with ID {player_id} to database")
        
        # Update player count in the database
        if room_id in game_stats:
            safe_record_stats(
                stats_db.record_game_start,
                game_id=game_stats[room_id]["game_id"], 
                num_players=len(game.players), 
                big_blind=game.big_blind
            )
    except Exception as e:
        print(f"Error recording player in database: {str(e)}")
        # Continue without statistics tracking if there's an error
        
    player_rooms[request.sid] = room_id
    player_names[request.sid] = player_name
    
    join_room(room_id)
    
    # Broadcast updated game state to all players in the room
    for player_sid in game.players:
        emit('game_state', game.get_game_state(player_sid), room=player_sid)
    
    # If there are 2 or more players and the game is in waiting state, start it
    if len(game.players) >= 2 and game.game_state == "waiting":
        success = game.start_new_round()
        if success:
            for player_sid in game.players:
                emit('game_state', game.get_game_state(player_sid), room=player_sid)

@socketio.on('player_action')
def handle_player_action(data):
    action = data.get('action')
    amount = data.get('amount', 0)
    
    sid = request.sid
    if sid not in player_rooms:
        emit('error', {'message': 'Player not in a room'})
        return
        
    room_id = player_rooms[sid]
    game = games[room_id]
    
    result, message = game.handle_player_action(sid, action, amount)
    if not result:
        emit('error', {'message': message})
        return
    
    # Record the action in the database
    try:
        if stats_enabled and room_id in game_stats and "current_hand_id" in game_stats[room_id]:
            player_name = player_names.get(sid)
            if player_name:
                # Get player ID directly using add_player which returns existing ID
                player_id = safe_record_stats(stats_db.add_player, player_name)
                
                if player_id:
                    # Record action with all required parameters
                    hand_id = game_stats[room_id].get("current_hand_id")
                    safe_record_stats(
                        stats_db.record_action,
                        hand_id=hand_id,
                        player_id=player_id,
                        action_type=action,
                        amount=int(amount) if amount else 0,
                        street=game.game_state
                    )
    except Exception as e:
        print(f"Error recording player action: {str(e)}")
        import traceback
        traceback.print_exc()
        # Continue game even if statistics recording fails
    
    # Broadcast updated game state to all players in the room
    for player_sid in game.players:
        emit('game_state', game.get_game_state(player_sid), room=player_sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle player disconnection with more robust tracking."""
    sid = request.sid
    print(f"\n=== PLAYER DISCONNECTED ===")
    print(f"Socket ID: {sid}")
    
    if sid not in player_rooms:
        print("Player was not in any room")
        print("=== DISCONNECT HANDLED ===\n")
        return
        
    room_id = player_rooms[sid]
    print(f"Player was in room {room_id}")
    
    # Get player name if available
    player_name = player_names.get(sid, "Unknown")
    print(f"Player name: {player_name}")
    
    if room_id not in games:
        print("Room no longer exists")
        if sid in player_rooms:
            del player_rooms[sid]
        if sid in player_names:
            del player_names[sid]
        print("=== DISCONNECT HANDLED ===\n")
        return
        
    game = games[room_id]
    
    # Mark the disconnection but handle actual removal differently based on game state
    if sid in game.players:
        game_phase = game.game_state
        print(f"Game phase: {game_phase}")
        
        # Clean up between rounds or during waiting
        if game_phase in ["waiting", "round_complete"]:
            print(f"Removing player immediately (between rounds)")
            if hasattr(game, 'remove_player'):
                game.remove_player(sid)
            else:
                del game.players[sid]
        else:
            # Flag that player as disconnected but leave in game until the round completes
            # This way their cards/bets remain in play until the hand finishes
            print(f"Player disconnected during active round - will be removed at next round")
            # We could mark the player somehow, but the disconnect is already tracked 
            # by removing them from player_rooms
    
    # Remove player from tracking maps
    del player_rooms[sid]
    if sid in player_names:
        del player_names[sid]
    
    # Check if all players are gone from the room
    active_player_count = sum(1 for player_id in game.players if player_id in player_rooms)
    print(f"Remaining active players in room: {active_player_count}")
    
    if active_player_count == 0:
        print("No active players left, cleaning up the room")
        # Record game end in the database if all players are gone
        if room_id in game_stats:
            try:
                safe_record_stats(
                    stats_db.record_game_end,
                    game_id=game_stats[room_id]["game_id"],
                    total_hands=game_stats[room_id]["hand_count"]
                )
                del game_stats[room_id]
            except Exception as e:
                print(f"Error recording game end: {str(e)}")
            
        del games[room_id]
    else:
        # Broadcast updated game state to remaining players
        print(f"Broadcasting updated state to remaining players")
        player_count = 0
        for player_sid in list(game.players.keys()):
            if player_sid in player_rooms:  # Only send to still-connected players
                emit('game_state', game.get_game_state(player_sid), room=player_sid)
                player_count += 1
        print(f"Sent updates to {player_count} players")
    
    print("=== DISCONNECT HANDLED ===\n")

if __name__ == '__main__':
    # Get the host's IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    print(f"\nServer starting...")
    print(f"Local IP Address: {local_ip}")
    print(f"Access the game at: http://{local_ip}:5000")
    print("Share this URL with other players to join your game!")
    print("\nNote: Make sure your firewall allows connections on port 5000")
    
    # Run the server on all network interfaces (0.0.0.0)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True) 