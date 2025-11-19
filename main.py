#!/usr/bin/env python3
"""
Example usage of Perplexity.ai automation
"""
from src.perplexity import ask_plexi


def main():
    """Example usage of ask_plexi()"""
    question = "Don't do any web research, just say hi to me!"
    
    print(f"Asking Perplexity.ai: {question}")
    print("=" * 60)
    
    try:
        response = ask_plexi(question)
        print("\nResponse:")
        print(response)
        print("\n" + "=" * 60)
        print("Response has been copied to clipboard.")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

