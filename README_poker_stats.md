# Poker Statistics Database

This is a Data Access Layer (DAL) for tracking poker game statistics. It allows you to record player performance, game history, and analyze playing patterns over time.

## Features

- **Player Statistics**: Track wins, losses, chip counts, and win rates
- **Game History**: Record details of each poker game session
- **Hand Tracking**: Store information about individual hands, including community cards and winners
- **Action Logging**: Track every player action (bet, call, fold, etc.)
- **Statistical Analysis**: Generate reports and visualize player performance

## Requirements

The following Python packages are required:
- sqlite3 (included in Python standard library)
- pandas
- matplotlib
- tabulate

Install dependencies with:
```
pip install pandas matplotlib tabulate
```

## Usage

### Running the Statistics Tool

To view and analyze poker statistics, run:
```
python poker_stats.py
```

This will start the interactive command-line tool that allows you to:
1. View player statistics
2. Browse hand history
3. Generate detailed player reports
4. Create performance charts

### Integration with Poker Game

To integrate this with your poker game, add the following code to your `server.py`:

```python
from poker_stats import PokerDatabase

# Initialize the database
db = PokerDatabase()

# In your game creation logic:
game_id = db.record_game_start(num_players=len(players), big_blind=game.big_blind)

# When a player joins:
player_id = db.add_player(player_name)

# When a hand starts:
hand_id = db.record_hand(
    game_id=game_id,
    hand_number=hand_count,
    pot_size=game.pot,
    flop=str(game.community_cards[:3]) if len(game.community_cards) >= 3 else None,
    turn=str(game.community_cards[3]) if len(game.community_cards) >= 4 else None,
    river=str(game.community_cards[4]) if len(game.community_cards) >= 5 else None
)

# When a player makes an action:
db.record_action(
    hand_id=hand_id,
    player_id=player_id,
    action_type=action,  # e.g., "bet", "call", "fold"
    amount=amount,
    street=game.game_state  # e.g., "preflop", "flop", etc.
)

# When a hand ends:
for player_id, player in game.players.items():
    db.record_player_hand(
        hand_id=hand_id,
        player_id=player_id,
        starting_chips=player["starting_chips"],
        ending_chips=player["chips"],
        cards=str(player["hand"]),
        position=player_position,
        is_winner=player["is_winner"],
        final_hand_type=get_hand_type(player["score"])
    )

# When the game ends:
db.record_game_end(game_id=game_id, total_hands=hand_count)
```

## Database Schema

The database consists of five main tables:

1. **players**: Basic player information and aggregate stats
2. **games**: Information about each game session
3. **hands**: Details about each poker hand played
4. **player_hands**: How each player performed in each hand
5. **actions**: Individual player actions during the game

## Example Reports

### Player Statistics
```
+-----------+-------+------+--------+-----------+------------+-------------+
| Username  | Games | Wins | Win %  | Chips Won | Chips Lost | Biggest Win |
+===========+=======+======+========+===========+============+=============+
| Sagnik    | 42    | 15   | 35.71  | 24650     | 12300      | 3500        |
+-----------+-------+------+--------+-----------+------------+-------------+
```

### Hand History
```
+---------+----------+----------+------------------+------+------+--------+--------+
| Hand ID | Hand #   | Pot Size | Flop             | Turn | River| Winner | Hand   |
+=========+==========+==========+==================+======+======+========+========+
| 124     | 7        | 560      | A♠ K♥ 10♦        | Q♠   | J♣   | Sagnik | Straight|
+---------+----------+----------+------------------+------+------+--------+--------+
```

## License

This project is open source and available under the MIT License. 