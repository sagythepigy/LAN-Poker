import sqlite3
import os
import shutil

def main():
    """Reset the database by:
    1. Backing up the existing database
    2. Creating a clean one
    """
    db_file = "poker_stats.db"
    
    # Check if database exists
    if os.path.exists(db_file):
        # Create backup
        backup_file = f"{db_file}.bak"
        print(f"Backing up existing database to {backup_file}")
        shutil.copy2(db_file, backup_file)
        
        # Remove existing database
        print(f"Removing existing database {db_file}")
        os.remove(db_file)
    
    # Create new database
    print(f"Creating new database {db_file}")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Create tables
    print("Creating tables...")
    
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
    
    # Create player_hands table
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
    
    # Create actions table
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
    
    conn.commit()
    conn.close()
    
    print(f"Database {db_file} has been reset successfully")

if __name__ == "__main__":
    main() 