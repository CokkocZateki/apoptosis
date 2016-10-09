#!/usr/bin/env python
import argparse

from apoptosis.http.server import main as http_main


parser = argparse.ArgumentParser(description='HKauth CLI frontend.')

parser.add_argument(
    '--http-server',
    dest='http_server',
    action='store_true',
    help='Run the HTTP server.'
)

def main():
    arguments = parser.parse_args()

    if arguments.http_server:
        http_main()

if __name__ == '__main__':
    main()
