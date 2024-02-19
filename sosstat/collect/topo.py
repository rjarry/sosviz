# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D


def parse_report(path: pathlib.Path, data: D):
    for node in path.glob("sys/devices/system/node/node*"):
        match = re.match(r"^node(\d+)$", node.name)
        if not match:
            continue

        numa_id = int(match.group(1))
        numa = data.setdefault("numa", D()).setdefault(numa_id, D(id=numa_id))

        match = re.search(r"MemTotal:\s+(\d+)\s*kB", (node / "meminfo").read_text())
        if match:
            numa.total_memory = int(match.group(1)) * 1024

        for huge in node.glob("hugepages/hugepages-*/nr_hugepages"):
            match = re.match(r"^hugepages-(\d+)kB$", huge.parent.name)
            if match:
                size = int(match.group(1)) * 1024
                numa.setdefault("hugepages", D())[size] = int(huge.read_text())

        siblings = D()
        cpus = set()
        for cpu in path.glob("sys/devices/system/cpu/cpu*/topology"):
            package_id = int((cpu / "physical_package_id").read_text())
            if package_id != numa_id:
                continue
            threads = set(
                int(t) for t in (cpu / "thread_siblings_list").read_text().split(",")
            )
            cpus.update(threads)
            for t in threads:
                siblings[t] = threads - {t}
        numa.cpus = cpus
        numa.thread_siblings = siblings
