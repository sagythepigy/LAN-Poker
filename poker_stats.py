import sqlite3
import os
import datetime
import pandas as pd
import matplotlib.pyplot as plt
from tabulate import tabulate

class PokerDatabase:
    def __init__(self, db_file="poker_stats.db", check_same_thread=False):
        self.db_file = db_file
        self.check_same_thread = check_same_thread
        self.conn = None
        self.setup_database()
        
    def setup_database(self):
        # Connect to the database (creates it if it doesn't exist)
        if self.conn is None:
            print(f"Connecting to database: {self.db_file}")
            self.conn = sqlite3.connect(self.db_file, check_same_thread=self.check_same_thread)
        
        # Create tables if they don't exist
        cursor = self.conn.cursor()
        
        # Create games table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            num_players INTEGER,
            big_blind INTEGER
        )
        ''')
        
        # Create players table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create hands table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS hands (
            hand_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            hand_number INTEGER,
            pot_size INTEGER,
            flop TEXT,
            turn TEXT,
            river TEXT,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES games (game_id)
        )
        ''')
        
        # Create player_hands table to track player hands in each game hand
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_hands (
            player_hand_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hand_id INTEGER,
            player_id INTEGER,
            starting_chips INTEGER,
            ending_chips INTEGER,
            cards TEXT,
            position INTEGER,
            is_winner BOOLEAN,
            final_hand_type TEXT,
            FOREIGN KEY (hand_id) REFERENCES hands (hand_id),
            FOREIGN KEY (player_id) REFERENCES players (player_id)
        )
        ''')
        
        # Create actions table to track individual actions
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hand_id INTEGER,
            player_id INTEGER,
            action_type TEXT,
            amount INTEGER,
            street TEXT,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (hand_id) REFERENCES hands (hand_id),
            FOREIGN KEY (player_id) REFERENCES players (player_id)
        )
        ''')
        
        self.conn.commit()
        print("Database setup complete - tables created if they didn't exist")
    
    def ensure_connection(self):
        """Ensure database connection is open"""
        try:
            # Test if connection is alive
            self.conn.execute("SELECT 1")
        except (sqlite3.Error, AttributeError):
            # Reopen the connection if it's closed
            print(f"Reopening database connection to {self.db_file}")
            self.conn = sqlite3.connect(self.db_file, check_same_thread=self.check_same_thread)
        return self.conn
    
    def add_player(self, username):
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO players (username) VALUES (?)", (username,))
            conn.commit()
            
            # Get the player_id (either the one just created or the existing one)
            cursor.execute("SELECT player_id FROM players WHERE username = ?", (username,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"Error adding player: {str(e)}")
            return None
    
    def record_game_start(self, game_id=None, num_players=0, big_blind=0):
        """Record a new game or update an existing game.
        If game_id is provided, update that game. Otherwise, create a new game."""
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            if game_id is None:
                # Create a new game
                cursor.execute(
                    "INSERT INTO games (num_players, big_blind) VALUES (?, ?)", 
                    (num_players, big_blind)
                )
                new_game_id = cursor.lastrowid
                conn.commit()
                return new_game_id
            else:
                # Update an existing game
                cursor.execute(
                    "UPDATE games SET num_players = ? WHERE game_id = ?", 
                    (num_players, game_id)
                )
                conn.commit()
                return game_id
        except Exception as e:
            print(f"Error in record_game_start: {str(e)}")
            return None
    
    def record_game_end(self, game_id, total_hands=0):
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE games SET end_time = CURRENT_TIMESTAMP WHERE game_id = ?", 
                (game_id,)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error recording game end: {str(e)}")
            return False
    
    def record_hand(self, game_id, hand_number, pot_size, flop=None, turn=None, river=None):
        print(f"Recording hand: game_id={game_id}, hand_number={hand_number}, pot={pot_size}")
        print(f"Community cards: flop={flop}, turn={turn}, river={river}")
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO hands (game_id, hand_number, pot_size, flop, turn, river) VALUES (?, ?, ?, ?, ?, ?)",
                (game_id, hand_number, pot_size, flop, turn, river)
            )
            conn.commit()
            hand_id = cursor.lastrowid
            print(f"Hand recorded successfully with ID: {hand_id}")
            return hand_id
        except Exception as e:
            print(f"Error recording hand: {str(e)}")
            return None
    
    def record_player_hand(self, hand_id, player_id, starting_chips, ending_chips, cards, position, is_winner, final_hand_type):
        print(f"Recording player hand: player_id={player_id}, hand_id={hand_id}, cards={cards}, winner={is_winner}")
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO player_hands (hand_id, player_id, starting_chips, ending_chips, cards, position, is_winner, final_hand_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (hand_id, player_id, starting_chips, ending_chips, cards, position, is_winner, final_hand_type)
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error recording player hand: {str(e)}")
            return None
    
    def record_action(self, hand_id, player_id, action_type, amount, street):
        print(f"Recording action: player_id={player_id}, hand_id={hand_id}, action={action_type}, amount={amount}")
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO actions (hand_id, player_id, action_type, amount, street) VALUES (?, ?, ?, ?, ?)",
                (hand_id, player_id, action_type, amount, street)
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error recording action: {str(e)}")
            return None

    def get_player_stats(self, username=None):
        """Get statistics for a player or all players"""
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            
            # First verify our tables exist and have data
            cursor.execute("SELECT COUNT(*) FROM players")
            player_count = cursor.fetchone()[0]
            if player_count == 0:
                print("No players found in database")
                return []
                
            # Build a query that correctly aggregates statistics
            stats_query = """
                SELECT 
                    p.username,
                    COUNT(DISTINCT h.game_id) AS total_games,
                    SUM(CASE WHEN ph.is_winner = 1 THEN 1 ELSE 0 END) AS wins,
                    CASE 
                        WHEN COUNT(DISTINCT ph.hand_id) > 0 
                        THEN ROUND((SUM(CASE WHEN ph.is_winner = 1 THEN 1 ELSE 0 END) * 100.0) / COUNT(DISTINCT ph.hand_id), 2) 
                        ELSE 0 
                    END AS win_percentage,
                    SUM(CASE WHEN ph.ending_chips > ph.starting_chips THEN ph.ending_chips - ph.starting_chips ELSE 0 END) AS total_chips_won,
                    SUM(CASE WHEN ph.ending_chips < ph.starting_chips THEN ph.starting_chips - ph.ending_chips ELSE 0 END) AS total_chips_lost,
                    MAX(CASE WHEN ph.ending_chips > ph.starting_chips THEN ph.ending_chips - ph.starting_chips ELSE 0 END) AS biggest_win
                FROM 
                    players p
                LEFT JOIN 
                    player_hands ph ON p.player_id = ph.player_id
                LEFT JOIN 
                    hands h ON ph.hand_id = h.hand_id
            """
            
            if username:
                stats_query += " WHERE p.username = ? GROUP BY p.username"
                cursor.execute(stats_query, (username,))
            else:
                stats_query += " GROUP BY p.username ORDER BY win_percentage DESC"
                cursor.execute(stats_query)
            
            results = cursor.fetchall()
            print(f"Player stats query returned {len(results)} results")
            return results
        except Exception as e:
            print(f"Error getting player stats: {str(e)}")
            return []

    def get_hand_history(self, game_id=None, limit=10):
        """Get the history of hands played"""
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            
            # Check if there is any hand data first
            cursor.execute("SELECT COUNT(*) FROM hands")
            hand_count = cursor.fetchone()[0]
            if hand_count == 0:
                print("No hands recorded in database")
                return []
            
            # Build query based on whether we want game-specific hands or overall history
            if game_id:
                query = """
                    SELECT 
                        h.hand_id,
                        h.hand_number,
                        h.pot_size,
                        h.flop,
                        h.turn,
                        h.river,
                        p.username as winner,
                        ph.final_hand_type
                    FROM hands h
                    LEFT JOIN player_hands ph ON h.hand_id = ph.hand_id AND ph.is_winner = 1
                    LEFT JOIN players p ON ph.player_id = p.player_id
                    WHERE h.game_id = ?
                    ORDER BY h.hand_id DESC
                    LIMIT ?
                """
                cursor.execute(query, (game_id, limit))
            else:
                query = """
                    SELECT 
                        h.hand_id,
                        h.game_id,
                        h.hand_number,
                        h.pot_size,
                        h.flop,
                        h.turn,
                        h.river,
                        p.username as winner,
                        ph.final_hand_type
                    FROM hands h
                    LEFT JOIN player_hands ph ON h.hand_id = ph.hand_id AND ph.is_winner = 1
                    LEFT JOIN players p ON ph.player_id = p.player_id
                    ORDER BY h.hand_id DESC
                    LIMIT ?
                """
                cursor.execute(query, (limit,))
            
            results = cursor.fetchall()
            print(f"Hand history query returned {len(results)} results")
            return results
        except Exception as e:
            print(f"Error getting hand history: {str(e)}")
            return []

    def get_player_hand_types(self, player_id):
        """Get the distribution of hand types for a player"""
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    final_hand_type,
                    COUNT(*) as count
                FROM player_hands
                WHERE player_id = ? AND final_hand_type IS NOT NULL
                GROUP BY final_hand_type
                ORDER BY count DESC
            """, (player_id,))
            
            return cursor.fetchall()
        except Exception as e:
            print(f"Error getting player hand types: {str(e)}")
            return []

    def generate_player_report(self, username):
        """Generate a detailed report for a player"""
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            
            # Get player ID
            cursor.execute("SELECT player_id FROM players WHERE username = ?", (username,))
            result = cursor.fetchone()
            if not result:
                return f"Player {username} not found"
            
            player_id = result[0]
            
            # Get basic stats
            stats = self.get_player_stats(username)
            if not stats:
                return f"No statistics found for player {username}"
            
            stats = stats[0]
            
            # Get hand type distribution
            hand_types = self.get_player_hand_types(player_id)
            
            # Get recent hands
            cursor.execute("""
                SELECT 
                    h.hand_number,
                    h.pot_size,
                    ph.cards,
                    ph.final_hand_type,
                    ph.is_winner,
                    ph.ending_chips - ph.starting_chips as profit
                FROM player_hands ph
                JOIN hands h ON ph.hand_id = h.hand_id
                WHERE ph.player_id = ?
                ORDER BY h.time DESC
                LIMIT 10
            """, (player_id,))
            
            recent_hands = cursor.fetchall()
            
            # Get betting patterns
            cursor.execute("""
                SELECT 
                    action_type,
                    COUNT(*) as count,
                    AVG(amount) as avg_amount
                FROM actions
                WHERE player_id = ? AND amount > 0
                GROUP BY action_type
            """, (player_id,))
            
            betting_patterns = cursor.fetchall()
            
            # Format the report
            report = f"=== Player Report: {username} ===\n\n"
            report += f"Games Played: {stats[1]}\n"
            report += f"Wins: {stats[2]} ({stats[3]}%)\n"
            report += f"Total Chips Won: {stats[4]}\n"
            report += f"Total Chips Lost: {stats[5]}\n"
            report += f"Biggest Win: {stats[6]}\n\n"
            
            report += "=== Hand Type Distribution ===\n"
            if hand_types:
                hand_types_table = tabulate(hand_types, headers=["Hand Type", "Count"], tablefmt="grid")
                report += hand_types_table + "\n\n"
            else:
                report += "No hand types recorded\n\n"
            
            report += "=== Recent Hands ===\n"
            if recent_hands:
                recent_hands_table = tabulate(
                    recent_hands, 
                    headers=["Hand #", "Pot Size", "Cards", "Hand Type", "Won?", "Profit"],
                    tablefmt="grid"
                )
                report += recent_hands_table + "\n\n"
            else:
                report += "No recent hands recorded\n\n"
            
            report += "=== Betting Patterns ===\n"
            if betting_patterns:
                betting_patterns_table = tabulate(
                    betting_patterns,
                    headers=["Action", "Count", "Avg Amount"],
                    tablefmt="grid"
                )
                report += betting_patterns_table + "\n\n"
            else:
                report += "No betting patterns recorded\n\n"
            
            return report
        except Exception as e:
            print(f"Error generating player report: {str(e)}")
            return f"Error generating report for {username}: {str(e)}"

    def plot_player_performance(self, username):
        """Generate performance charts for a player"""
        try:
            conn = self.ensure_connection()
            cursor = conn.cursor()
            
            # Get player ID
            cursor.execute("SELECT player_id FROM players WHERE username = ?", (username,))
            result = cursor.fetchone()
            if not result:
                return f"Player {username} not found"
            
            player_id = result[0]
            
            # Get chip history
            cursor.execute("""
                SELECT 
                    h.time,
                    ph.ending_chips - ph.starting_chips as profit
                FROM player_hands ph
                JOIN hands h ON ph.hand_id = h.hand_id
                WHERE ph.player_id = ?
                ORDER BY h.time
            """, (player_id,))
            
            results = cursor.fetchall()
            if not results:
                return f"No hand history found for player {username}"
            
            # Create dataframe
            df = pd.DataFrame(results, columns=["timestamp", "profit"])
            df['cumulative_profit'] = df['profit'].cumsum()
            
            # Plot cumulative profit
            plt.figure(figsize=(12, 6))
            plt.plot(df['timestamp'], df['cumulative_profit'], marker='o')
            plt.title(f"{username}'s Cumulative Profit Over Time")
            plt.xlabel("Time")
            plt.ylabel("Cumulative Profit (Chips)")
            plt.grid(True)
            plt.tight_layout()
            
            # Save plot
            plot_file = f"{username}_performance.png"
            plt.savefig(plot_file)
            plt.close()
            
            return f"Performance chart saved to {plot_file}"
        except Exception as e:
            print(f"Error plotting player performance: {str(e)}")
            return f"Error creating performance chart for {username}: {str(e)}"
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            print("Database connection closed")

def main():
    """Main function for running the poker statistics tool"""
    db = PokerDatabase()
    
    while True:
        print("\n=== Poker Statistics Tool ===")
        print("1. View Player Statistics")
        print("2. View Hand History")
        print("3. Generate Player Report")
        print("4. Plot Player Performance")
        print("5. Exit")
        
        choice = input("Enter your choice (1-5): ")
        
        if choice == "1":
            username = input("Enter player username (or press Enter for all players): ")
            if username:
                stats = db.get_player_stats(username)
                if stats:
                    print(tabulate([stats[0]], headers=["Username", "Games", "Wins", "Win %", "Chips Won", "Chips Lost", "Biggest Win"], tablefmt="grid"))
                else:
                    print(f"No statistics found for player {username}")
            else:
                stats = db.get_player_stats()
                print(tabulate(stats, headers=["Username", "Games", "Wins", "Win %", "Chips Won", "Chips Lost", "Biggest Win"], tablefmt="grid"))
        
        elif choice == "2":
            game_id = input("Enter game ID (or press Enter for all games): ")
            if game_id and game_id.isdigit():
                history = db.get_hand_history(int(game_id))
                if history:
                    print(tabulate(history, headers=["Hand ID", "Hand #", "Pot Size", "Flop", "Turn", "River", "Winner", "Hand Type"], tablefmt="grid"))
                else:
                    print(f"No hand history found for game {game_id}")
            else:
                history = db.get_hand_history()
                if history:
                    print(tabulate(history, headers=["Hand ID", "Game ID", "Hand #", "Pot Size", "Flop", "Turn", "River", "Winner", "Hand Type"], tablefmt="grid"))
                else:
                    print("No hand history found")
        
        elif choice == "3":
            username = input("Enter player username: ")
            report = db.generate_player_report(username)
            print(report)
        
        elif choice == "4":
            username = input("Enter player username: ")
            result = db.plot_player_performance(username)
            print(result)
        
        elif choice == "5":
            db.close()
            print("Goodbye!")
            break
        
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main() 