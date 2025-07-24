#!/opt/homebrew/bin/python3
# filepath: /Users/chuck.sumner/workspace/chuck-working/pp/passphrase.py
import secrets
import os
import argparse
import sys
from typing import Dict, List


def load_wordlist(filepath: str) -> Dict[str, str]:
    """Load the EFF wordlist from a file."""
    words = {}
    with open(filepath) as wordlist:
        for line in wordlist:
            parts = line.strip().split()
            if len(parts) >= 2:
                words[parts[0]] = parts[1]
    
    if not words:
        raise ValueError(f"No words loaded from wordlist: {filepath}")
    return words


def generate_dice_roll() -> str:
    """Generate a 5-dice roll combination."""
    return "".join(str(secrets.randbelow(6) + 1) for _ in range(5))


def generate_passphrase(length: int, wordlist: Dict[str, str], separator: str = " ") -> str:
    """Generate a single passphrase of specified length."""
    return separator.join(
        wordlist.get(generate_dice_roll(), "???") 
        for _ in range(length)
    )


def generate_passphrases(length: int, count: int = 5, separator: str = " ", wordlist_path: str = None) -> List[str]:
    """Generate multiple passphrases."""
    if length < 1:
        raise ValueError("Length must be a positive integer")
    if count < 1:
        raise ValueError("Count must be a positive integer")
    
    if not wordlist_path:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        wordlist_path = os.path.join(script_dir, "eff_large_wordlist.txt")
    
    wordlist = load_wordlist(wordlist_path)
    return [generate_passphrase(length, wordlist, separator) for _ in range(count)]


def main():
    """Handle command-line arguments and generate passphrases."""
    parser = argparse.ArgumentParser(description="Generate secure passphrases using the EFF wordlist")
    parser.add_argument("length", type=int, nargs="?", default=4, 
                      help="Number of words in each passphrase (default: 4)")
    parser.add_argument("-c", "--count", type=int, default=5,
                      help="Number of passphrases to generate (default: 5)")
    parser.add_argument("-s", "--separator", type=str, default=" ",
                      help="Separator between words (default: space)")
    parser.add_argument("-w", "--wordlist", type=str,
                      help="Path to custom wordlist file")
    args = parser.parse_args()
    
    try:
        passphrases = generate_passphrases(
            args.length, 
            args.count, 
            args.separator,
            args.wordlist
        )
        for passphrase in passphrases:
            print(passphrase)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    exit(main())