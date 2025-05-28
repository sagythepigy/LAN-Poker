# Texas Hold'em Poker Game

A fully-featured multiplayer Texas Hold'em poker game with web interface and statistics tracking.

## Features

- Real-time multiplayer poker through web browser
- Complete Texas Hold'em rules and hand evaluation
- Player statistics tracking and analysis
- Support for up to 8 players
- Standard betting actions (check, call, raise, fold, all-in)
- Hand rankings from High Card to Royal Flush
- Side pot handling for all-in situations
- Game state persistence and automatic round transitions

## Setup

1. Make sure you have Python 3.7+ installed
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. For statistics tracking (optional):
   ```bash
   pip install pandas matplotlib tabulate
   ```

## Running the Game

1. Start the server:
   ```bash
   python server.py
   ```
2. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```
3. Create a room or join an existing one
4. Share the room ID with friends to play together

## Game Rules

This implementation follows standard Texas Hold'em rules:
- Each player starts with 10,000 chips
- Small blind is 10 chips
- Big blind is 20 chips
- Game flow: preflop → flop → turn → river → showdown
- Standard hand rankings apply
- Player with the best five-card hand wins

## Statistics Tracking

The game includes a built-in statistics tracking system that records:
- Player performance (win rates, chips won/lost)
- Hand history
- Betting patterns
- Hand type distributions

To view statistics:
```bash
python poker_stats.py
```

## Project Structure

- `server.py` - Main game server and poker logic
- `templates/` - HTML templates for the web interface
- `poker_stats.py` - Statistics database and analysis tools

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 