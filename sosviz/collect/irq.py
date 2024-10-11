# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D
from ..bits import parse_cpu_set


CPU_RE = re.compile(r"\bCPU(\d+)\b")
INTERRUPT_RE = re.compile(r"^\s*(\w+):\s+([\s\d]+)\s+([A-Za-z].+)$")


def parse_report(path: pathlib.Path, data: D):
    data.irqs = irqs = D()
    data.cpus = cpus = D()
    f = path / "proc/interrupts"
    if not f.is_file():
        return

    topo_cpu_ids = []
    for cpu in path.glob("sys/devices/system/cpu/cpu[0-9]*"):
        topo_cpu_ids.append(int(re.match(r"cpu(\d+)", cpu.name).group(1)))

    interrupts = f.read_text().splitlines()
    irq_cpu_ids = [int(c) for c in CPU_RE.findall(interrupts.pop(0))]
    counters_len = max(*irq_cpu_ids, *topo_cpu_ids) + 1

    for line in interrupts:
        match = INTERRUPT_RE.match(line)
        if match is None:
            continue
        irq = match.group(1)
        counters = [0] * counters_len
        for i, c in enumerate(match.group(2).split()):
            counters[irq_cpu_ids[i]] = int(c)
        irqs[irq] = D(
            irq=irq,
            desc=re.sub(r"\s+", " ", match.group(3).strip()),
            counters=counters,
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
