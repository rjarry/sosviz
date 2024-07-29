# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D
from ..bits import parse_cpu_set


def parse_report(path: pathlib.Path, data: D):
    nodes = list(path.glob("sys/devices/system/node/node[0-9]*"))
    for node in nodes:
        match = re.match(r"^node(\d+)$", node.name)
        if not match:
            continue

        numa_id = int(match.group(1))
        numa = data.setdefault("numa", D()).setdefault(numa_id, D(id=numa_id))

        cpus = parse_cpu_set((node / "cpulist").read_text())
        siblings = D()

        try:
            div = 1
            meminfo = (node / "meminfo").read_text()
        except FileNotFoundError:
            div = len(nodes)
            meminfo = (path / "proc/meminfo").read_text()

        match = re.search(r"MemTotal:\s+(\d+)\s*kB", meminfo)
        if match:
            numa.total_memory = int(int(match.group(1)) * 1024 / div)

        for huge in node.glob("hugepages/hugepages-*/nr_hugepages"):
            match = re.match(r"^hugepages-(\d+)kB$", huge.parent.name)
            if match:
                size = int(match.group(1)) * 1024
                numa.setdefault("hugepages", D())[size] = int(huge.read_text())

        offline_cpus = set()
        for cpu in path.glob("sys/devices/system/cpu/cpu[0-9]*"):
            if not (cpu / f"node{numa_id}").is_dir():
                continue
            cpu_id = int(re.match(r"cpu(\d+)", cpu.name).group(1))
            online = cpu / "online"
            if online.is_file() and online.read_text().strip() == "0":
                offline_cpus.add(cpu_id)
                continue
            topo = cpu / "topology"
            try:
                threads = parse_cpu_set((topo / "thread_siblings_list").read_text())
            except FileNotFoundError:
                try:
                    threads = parse_cpu_set((topo / "core_cpus_list").read_text())
                except FileNotFoundError:
                    # hyperthreading disabled
                    continue
            for t in threads:
                siblings[t] = threads - {t}
        numa.cpus = cpus
        numa.offline_cpus = offline_cpus
        numa.thread_siblings = siblings
