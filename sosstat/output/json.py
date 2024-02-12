# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import json


def render(report, **opts):
    print(json.dumps(report, indent=2))
