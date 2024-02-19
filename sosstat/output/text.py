# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import os
import pprint


def render(report, **opts):
    try:
        width, _ = os.get_terminal_size()
    except OSError:
        width = 100
    pprint.pprint(report, compact=True, width=width)
