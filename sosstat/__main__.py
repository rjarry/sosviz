# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

"""
Collect information from an sosreport and export it in other formats.
"""

import argparse
import pathlib
import sys

from . import collect, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        metavar="PATH",
        type=pathlib.Path,
        help="""
        Path to an uncompressed sosreport folder.
        """,
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="""
        Show debug info.
        """,
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=output.FORMATS.keys(),
        default=output.DEFAULT_FORMAT,
        help="""
        Output format (default: %(default)s).
        """,
    )
    args = parser.parse_args()
    try:
        if not args.path.is_dir():
            raise ValueError(f"'{args.path}': No such directory")
        report = collect.parse_report(args.path)
        output.render(report, args.format)
    except Exception as e:
        if args.debug or isinstance(e, NotImplementedError):
            raise
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
