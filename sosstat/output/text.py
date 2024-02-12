# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pprint


def render(report, **opts):
    pprint.pprint(report, compact=True, width=100)
