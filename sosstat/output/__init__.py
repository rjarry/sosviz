# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

from . import dot, text


FORMATS = {
    "dot": dot,
    "text": text,
}
DEFAULT_FORMAT = "text"


def render(report, fmt: str = DEFAULT_FORMAT, **opts):
    if fmt not in FORMATS:
        raise ValueError(f"unknown format: {fmt}")
    FORMATS[fmt].render(report, **opts)
