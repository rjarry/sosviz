# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re


def parse_report(path: pathlib.Path, data: dict):
    for node in path.glob("sys/devices/system/node/node*"):
        match = re.match(r"^node(\d+)$", node.name)
        if not match:
            continue

        numa_id = int(match.group(1))
        numa = data.setdefault("numa", {}).setdefault(numa_id, {})

        match = re.search(r"MemTotal:\s+(\d+)\s*kB", (node / "meminfo").read_text())
        if match:
            numa["total_memory"] = int(match.group(1)) * 1024

        for huge in node.glob("hugepages/hugepages-*/nr_hugepages"):
            match = re.match(r"^hugepages-(\d+)kB$", huge.parent.name)
            if match:
                size = int(match.group(1)) * 1024
                numa.setdefault("hugepages", {})[size] = int(huge.read_text())

        cpu_pairs = set()
        for cpu in path.glob("sys/devices/system/cpu/cpu*/topology"):
            package_id = int((cpu / "physical_package_id").read_text())
            if package_id != numa_id:
                continue
            threads = (cpu / "thread_siblings_list").read_text().split(",")
            cpu_pairs.add(frozenset(int(t) for t in threads))
        numa["cpus"] = sorted(tuple(sorted(p)) for p in cpu_pairs)
