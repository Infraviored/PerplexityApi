#!/usr/bin/env python3
"""
TimeButler Automation Service

A modular system for automating TimeButler time tracking.
"""
import argparse
import sys

from timebutler.app import TimeButlerApp

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='TimeButler Automation Service')
    parser.add_argument('--config', '-c', 
                        help='Path to config.json file')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    return parser.parse_args()

def main():
    """Main entry point"""
    print("[AUTO] Starting TimeButler automation service...")
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Start the TimeButler automation
    app = TimeButlerApp(config_path=args.config)
    
    # If debug mode is enabled, update config
    if args.debug:
        import logging
        app.config._config['logging']['level'] = logging.DEBUG
        app.log_manager._configure_logging()
    
    # Start the application
    result = app.start()
    if isinstance(result, bool):
        sys.exit(0 if result is True else 1)
    if isinstance(result, int):
        sys.exit(result)
    sys.exit(1)

if __name__ == "__main__":
    main()
