# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re


def parse_report(path: pathlib.Path, data: dict):
    for node in path.glob("sys/devices/system/node/node*"):
        match = re.match(r"node(\d+)", node.name)
        if not match:
            continue

        numa_id = int(match.group(1))

        numa = data.setdefault("numa", {}).setdefault(numa_id, {})
        nics = numa.setdefault("pci_nics", {})

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

            nic = nics.setdefault(pci_id, {})
            nic["pci_id"] = pci_id
            nic["device"] = match.group(2)
            k = re.search(r"^\tKernel driver in use: (.+)$", block, flags=re.MULTILINE)
            if k is not None:
                nic["kernel_driver"] = k.group(1)
