#!/opt/homebrew/bin/python3
import secrets

def generate_password(length):
    """Generate a password of specified length using EFF wordlist."""
    if not isinstance(length, int) or length < 1:
        raise ValueError("Length must be a positive integer")

    for _ in range(5):
        dice_rolls = {}
        password_words = []
        for x in range(length):
            # Generate 5 dice rolls (1-6)
            dice_rolls[x] = "".join(str(secrets.randbelow(6) + 1) for _ in range(5))
            password_words.append(words.get(dice_rolls[x], "???"))
        print(" ".join(password_words))


# Load the EFF wordlist
words = {}
with open("eff_large_wordlist.txt") as wordlist:
    for line in wordlist:
        score, word = line.strip().split()
        words[score] = word

if __name__ == "__main__":
    generate_password(4)
    print()
    generate_password(5)
    print()
    generate_password(6)
