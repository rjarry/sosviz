# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D
from ..bits import parse_cpu_set


INTERRUPT_RE = re.compile(r"^\s*(\w+):\s+([\s\d]+)\s+([A-Za-z].+)$", re.MULTILINE)


def parse_report(path: pathlib.Path, data: D):
    data.irqs = irqs = D()
    data.cpus = cpus = D()
    f = path / "proc/interrupts"
    if not f.is_file():
        return

    for match in INTERRUPT_RE.finditer(f.read_text()):
        irq, counters, desc = match.groups()
        irqs[irq] = D(
            irq=irq,
            desc=re.sub(r"\s+", " ", desc.strip()),
            counters=[int(c) for c in counters.split()],
        )
        try:
            irqs[irq].requested_affinity = parse_cpu_set(
                (path / f"proc/irq/{irq}/smp_affinity_list").read_text()
            )
            for cpu in irqs[irq].requested_affinity:
                c = cpus.setdefault(cpu, D(cpu=cpu))
                if "requested_irqs" in c:
                    c.requested_irqs += 1
                else:
                    c.requested_irqs = 1
            irqs[irq].effective_affinity = parse_cpu_set(
                (path / f"proc/irq/{irq}/effective_affinity_list").read_text()
            )
            for cpu in irqs[irq].effective_affinity:
                c = cpus.setdefault(cpu, D(cpu=cpu))
                if "effective_irqs" in c:
                    c.effective_irqs += 1
                else:
                    c.effective_irqs = 1
        except FileNotFoundError:
            pass
