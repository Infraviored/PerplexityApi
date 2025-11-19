#!/usr/bin/env python3
"""
Example usage of Perplexity.ai automation
"""
from src.perplexity import ask_plexi
import argparse

# add argparse to get question from command line
parser = argparse.ArgumentParser(description='Perplexity.ai automation')
parser.add_argument('question', nargs='?', type=str, default="Don't do any web research, just say hi to me!", help='The question to ask Perplexity.ai')
# add headless argument
parser.add_argument('--headless', action='store_true', help='Run in headless mode')
args = parser.parse_args()

def main():
    """Example usage of ask_plexi()"""
    question = args.question
    headless = args.headless
    print(f"Asking Perplexity.ai: {question}")
    print("=" * 60)
    
    try:
        # Use headless=True by default, but allow override via config
        response = ask_plexi(question, debug=True, headless=headless)
        print("\nResponse:")
        print(response)
        print("\n" + "=" * 60)
        print("Response has been copied to clipboard.")
    except Exception as e:
        print(f"Error: {e}")
        print("\nIf you see HTML dump messages above, check the debug_dumps/ directory for details.")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

