# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D
from ..bits import parse_cpu_set


VARIABLE_RE = re.compile(r"^(\w+)\s*=\s*(.+)$", re.MULTILINE)


def parse_report(path: pathlib.Path, data: D):
    cmdline = (path / "proc/cmdline").read_text()
    tuning = D()
    for prop in "isolcpus", "nohz_full", "rcu_nocbs":
        match = re.search(rf"{prop}=([0-9,-]+)", cmdline)
        if match:
            tuning[prop] = parse_cpu_set(match.group(1))

    tuned_profile = path / "etc/tuned/active_profile"
    if tuned_profile.is_file():
        profile = tuned_profile.read_text().strip()
        tuning.tuned = D(profile=profile, variables=D())
        variables = path / f"etc/tuned/{profile}-variables.conf"
        if variables.is_file():
            for match in VARIABLE_RE.finditer(variables.read_text()):
                tuning.tuned.variables[match.group(1)] = match.group(2)

    irqbalance = path / "etc/sysconfig/irqbalance"
    if irqbalance.is_file():
        cpus = set()
        for match in VARIABLE_RE.finditer(irqbalance.read_text()):
            name, value = match.groups()
            if name == "IRQBALANCE_BANNED_CPULIST":
                cpus.update(parse_cpu_set(value))
            elif name == "IRQBALANCE_BANNED_CPUS":
                value = "0x" + value.replace(",", "").strip()
                cpus.update(parse_cpu_set(value))
        tuning.irq_banned_cpus = cpus

    data.tuning = tuning
