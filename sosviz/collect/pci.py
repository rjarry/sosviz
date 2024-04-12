# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D


def parse_report(path: pathlib.Path, data: dict):
    bridges = pci_bridges(path)
    for node in path.glob("sys/devices/system/node/node*"):
        match = re.match(r"node(\d+)", node.name)
        if not match:
            continue

        numa_id = int(match.group(1))
        numa = data.setdefault("numa", D()).setdefault(numa_id, D(id=numa_id))
        nics = numa.setdefault("pci_nics", D())

        lspci = (path / "sos_commands/pci/lspci_-nnvv").read_text()
        for block in lspci.split("\n\n"):
            if not re.search(rf"^\tNUMA node: {numa_id}$", block, flags=re.MULTILINE):
                continue

            match = re.search(
                r"^([a-f0-9:\.]+) Ethernet controller \[0200\]: (.*)$",
                block,
                flags=re.MULTILINE,
            )
            if not match:
                continue

            pci_id = match.group(1)
            if len(pci_id) != len("0000:00:00.0"):
                pci_id = "0000:" + pci_id

            nic = nics.setdefault(pci_id, D())
            nic.pci_id = pci_id
            nic.device = match.group(2)
            k = re.search(r"^\tKernel driver in use: (.+)$", block, flags=re.MULTILINE)
            if k is not None:
                nic.kernel_driver = k.group(1)
            for net in path.glob(f"sys/devices/pci*/*/{pci_id}/net/*"):
                nic.netdev = net.name
            nic.pci_bridge = bridges.get(nic.pci_id[: len("0000:00")])


PCI_TREE_L1 = r"^[\s-][\+\\]-\[(?P<l1>[a-f\d]{4}:[a-f\d]{2})\]-"
PCI_TREE_L2 = r"^[\|\s]*[\+\\]-(?P<l2>[a-f\d]{2}\.[a-f\d])"
PCI_TREE_L3 = r"^[\|\s]*-\[(?P<l3start>[a-f\d]{2})(?:-(?P<l3end>[a-f\d]{2}))?\]"


def pci_bridges(path: pathlib.Path) -> dict:
    bridges = {}
    l1 = None
    l2 = None

    for line in (path / "sos_commands/pci/lspci_-tv").read_text().splitlines():
        match = re.search(PCI_TREE_L1, line)
        if match:
            l1 = match.group("l1")
            line = line[match.end() :]
        match = re.search(PCI_TREE_L2, line)
        if match:
            l2 = match.group("l2")
            line = line[match.end() :]
        match = re.search(PCI_TREE_L3, line)
        if match and l1 and l2:
            l3start = match.group("l3start")
            l3end = match.group("l3end") or l3start
            start = int(l3start, 16)
            end = int(l3end, 16)
            bridge_addr = f"{l1}:{l2}"
            domain, _, _ = l1.partition(":")
            for prefix in range(start, end + 1):
                bridges[f"{domain}:{prefix:02x}"] = bridge_addr

    return bridges
