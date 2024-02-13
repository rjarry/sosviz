# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from ..bits import parse_cpu_set


def parse_report(path: pathlib.Path, data: dict):
    cmdline = (path / "proc/cmdline").read_text()
    kernel = {
        "cmdline": cmdline,
    }

    for prop in "isolcpus", "nohz_full", "rcu_nocbs":
        match = re.search(rf"{prop}=([0-9,-]+)", cmdline)
        if match:
            kernel[prop] = parse_cpu_set(match.group(1))

    data["kernel"] = kernel
