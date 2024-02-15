# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import json


def render(report, **opts):
    print(json.dumps(report, default=cast_json))


def cast_json(obj):
    if isinstance(obj, set):
        return list(obj)
    return obj
