#!/usr/bin/python3

import sys
import argparse
import libamp


def main():
    # Build argument parser
    parser = argparse.ArgumentParser(description="Control Cambridge Audio amplifiers.")
    parser.add_argument("--pin", nargs="?", default=23, type=int)
    parser.add_argument("--repeat", nargs="?", default=1, type=libamp.posint)
    parser.add_argument("--model", default="540A", choices=libamp.all_models)
    parser.add_argument(
        "command",
        nargs=1,
        choices=libamp.all_commands,
        help="Not all commands are available for all models!",
    )
    args = parser.parse_args()

    command = args.command[0].lower()
    print("Sending '" + command + "' command to pin " + str(args.pin))

    if args.repeat != 1:
        print(str(args.repeat) + " times")

    libamp.execute(args.pin, command, args.repeat, model=args.model)


if __name__ == "__main__":
    sys.exit(main())
