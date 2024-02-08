# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

"""
Collect information from an sosreport and export it in other formats.
"""

import argparse
import sys

from . import collect, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        metavar="PATH",
        help="""
        Path to an sosreport. Can be either a folder or a compressed archive.
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
        report = collect.parse_report(args.path)
        output.render(report, args.format)
    except Exception as e:
        if args.debug:
            raise
        print(f"error: {e!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
