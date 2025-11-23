#!/usr/bin/env python3
"""
Entry point for Perplexity API server
"""
import argparse
import logging
from src.server import start_server

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Perplexity.ai API Server')
    parser.add_argument('--host', type=str, default='localhost', help='Host to bind to (default: localhost)')
    parser.add_argument('--port', type=int, default=8000, help='Port to listen on (default: 8000)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    start_server(host=args.host, port=args.port)

