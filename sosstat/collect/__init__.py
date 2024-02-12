# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import importlib
import pathlib
import pkgutil


def parse_report(path: pathlib.Path) -> dict:
    data = {}
    for collector in discover_collectors():
        collector.parse_report(path, data)
    return data


def discover_collectors():
    for info in pkgutil.walk_packages(__path__, prefix=__name__ + "."):
        mod = importlib.import_module(info.name, __name__)
        if not (hasattr(mod, "parse_report") and callable(mod.parse_report)):
            continue
        yield mod
