from game import PokerGame

def main():
    # Get number of players
    while True:
        try:
            num_players = int(input("Enter number of players (2-10): "))
            if 2 <= num_players <= 10:
                break
            print("Please enter a number between 2 and 10.")
        except ValueError:
            print("Please enter a valid number.")

    # Get player names
    player_names = []
    for i in range(num_players):
        name = input(f"Enter name for Player {i+1}: ")
        player_names.append(name)

    # Create and start game
    game = PokerGame(player_names)
    
    while True:
        print("\n=== Starting New Hand ===")
        game.start_new_hand()
        print(game)  # Show initial state
        
        # Deal flop
        input("\nPress Enter to deal the flop...")
        game.deal_flop()
        print(game)
        
        # Deal turn
        input("\nPress Enter to deal the turn...")
        game.deal_turn()
        print(game)
        
        # Deal river
        input("\nPress Enter to deal the river...")
        game.deal_river()
        print(game)
        
        # Ask if players want to continue
        play_again = input("\nPlay another hand? (y/n): ").lower()
        if play_again != 'y':
            break

    print("\nGame Over!")

if __name__ == "__main__":
    main() 