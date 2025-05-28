import sqlite3
import os

def main():
    """Check the poker_stats.db database tables and contents"""
    db_file = "poker_stats.db"
    
    if not os.path.exists(db_file):
        print(f"Database file {db_file} not found!")
        return
        
    print(f"Database file {db_file} exists, size: {os.path.getsize(db_file)} bytes")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"\nFound {len(tables)} tables in the database:")
        for i, table in enumerate(tables, 1):
            table_name = table[0]
            print(f"{i}. {table_name}")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            print(f"   - Total rows: {row_count}")
        
        # Show players table
        print("\n=== Players table ===")
        cursor.execute("SELECT * FROM players")
        rows = cursor.fetchall()
        if rows:
            print("player_id | username | join_date")
            print("-" * 50)
            for row in rows:
                print(f"{row[0]} | {row[1]} | {row[2]}")
        else:
            print("No players found")
            
        # Show games table
        print("\n=== Games table ===")
        cursor.execute("SELECT * FROM games")
        rows = cursor.fetchall()
        if rows:
            print("game_id | start_time | end_time | num_players | big_blind")
            print("-" * 70)
            for row in rows:
                print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]}")
        else:
            print("No games found")
            
        # Show hands table
        print("\n=== Hands table ===")
        cursor.execute("SELECT * FROM hands")
        rows = cursor.fetchall()
        if rows:
            print("hand_id | game_id | hand_number | pot_size | flop | turn | river | time")
            print("-" * 80)
            for row in rows:
                print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]}")
        else:
            print("No hands found")
            
        # Show player_hands table
        print("\n=== Player hands table ===")
        cursor.execute("SELECT * FROM player_hands")
        rows = cursor.fetchall()
        if rows:
            print("player_hand_id | hand_id | player_id | starting_chips | ending_chips | cards | position | is_winner | final_hand_type")
            print("-" * 120)
            for row in rows:
                print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} | {row[8]}")
        else:
            print("No player hands found")
            
        # Show actions table
        print("\n=== Actions table ===")
        cursor.execute("SELECT * FROM actions")
        rows = cursor.fetchall()
        if rows:
            print("action_id | hand_id | player_id | action_type | amount | street | time")
            print("-" * 90)
            for row in rows:
                print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]}")
        else:
            print("No actions found")
        
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main() 