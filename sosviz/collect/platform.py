# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D


def parse_report(path: pathlib.Path, data: D):
    data.hardware = hw = D(system="Unknown Hardware", processor=[], memory=[])
    f = path / "sos_commands/hardware/dmidecode"
    if not f.is_file():
        return
    dmi = f.read_text()
    blocks = re.split(
        r"^Handle 0x[a-fA-F0-9]+, DMI type \d+, \d+ bytes$", dmi, flags=re.MULTILINE
    )
    for block in blocks:
        if "\n" not in block.strip():
            continue
        name, block = block.strip().split("\n", 1)
        if name == "System Information":
            b = split_block(block)
            hw.system = f"{b.Manufacturer} {b['Product Name']}"

        elif name == "Memory Device":
            b = split_block(block)
            if "Speed" not in b:
                continue
            hw.memory.append(
                D(
                    type=f"{b.Type} {b['Type Detail']}",
                    size=b.Size,
                    slot=b.Locator,
                    speed=b.Speed,
                )
            )

        elif name == "Processor Information":
            b = split_block(block)
            props = {"Socket Designation", "Version", "Core Enabled", "Thread Count"}
            if not props.issubset(b.keys()):
                continue
            hw.processor.append(
                D(
                    slot=b["Socket Designation"],
                    model=b.Version,
                    cores=int(b["Core Enabled"]),
                    threads=int(b["Thread Count"]),
                )
            )


def split_block(block: str) -> D:
    fields = D()
    for match in re.finditer(r"^\t([\w\s-]+):\s(.*)$", block, flags=re.MULTILINE):
        fields[match.group(1).strip()] = match.group(2).strip()
    return fields
