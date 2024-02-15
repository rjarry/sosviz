# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from ..bits import parse_cpu_set


INTERRUPT_RE = re.compile(r"^\s*(\w+):\s+([\s\d]+)\s+([A-Za-z].+)$", re.MULTILINE)


def parse_report(path: pathlib.Path, data: dict):
    buf = (path / "proc/interrupts").read_text()
    irqs = {}
    cpus = {}
    for match in INTERRUPT_RE.finditer(buf):
        irq, counters, desc = match.groups()
        irqs[irq] = {
            "irq": irq,
            "desc": re.sub(r"\s+", " ", desc.strip()),
            "counters": [int(c) for c in counters.split()],
        }
        try:
            irqs[irq]["requested_affinity"] = parse_cpu_set(
                (path / f"proc/irq/{irq}/smp_affinity_list").read_text()
            )
            for cpu in irqs[irq]["requested_affinity"]:
                c = cpus.setdefault(cpu, {"cpu": cpu})
                if "requested_irqs" in c:
                    c["requested_irqs"] += 1
                else:
                    c["requested_irqs"] = 1
            irqs[irq]["effective_affinity"] = parse_cpu_set(
                (path / f"proc/irq/{irq}/effective_affinity_list").read_text()
            )
            for cpu in irqs[irq]["effective_affinity"]:
                c = cpus.setdefault(cpu, {"cpu": cpu})
                if "effective_irqs" in c:
                    c["effective_irqs"] += 1
                else:
                    c["effective_irqs"] = 1
        except FileNotFoundError:
            pass

    data["irq"] = {"irqs": irqs, "cpus": cpus}
