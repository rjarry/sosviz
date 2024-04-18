# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import re
import typing


HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
RANGE_RE = re.compile(r"\d+-\d+")
INT_RE = re.compile(r"\d+")


def parse_cpu_set(arg: str) -> typing.Set[int]:
    bit_ids = set()

    for item in arg.strip().split(","):
        if not item:
            continue
        if HEX_RE.match(item):
            item = int(item, 16)
            bit = 0
            while item != 0:
                if item & 1:
                    bit_ids.add(bit)
                bit += 1
                item >>= 1
        elif RANGE_RE.match(item):
            start, end = item.split("-")
            bit_ids.update(range(int(start, 10), int(end, 10) + 1))
        elif INT_RE.match(item):
            bit_ids.add(int(item, 10))
        else:
            raise ValueError(f"invalid cpu set: {item}")
    return bit_ids


def hex_mask(bit_ids: typing.Set[int]) -> str:
    mask = 0
    for bit in bit_ids:
        mask |= 1 << bit
    return hex(mask)


def bit_mask(bit_ids: typing.Set[int]) -> str:
    mask = 0
    for bit in bit_ids:
        mask |= 1 << bit
    return f"0b{mask:_b}"


def bit_list(bit_ids: typing.Set[int]) -> str:
    groups = []
    bit_ids = sorted(bit_ids)
    i = 0
    while i < len(bit_ids):
        low = bit_ids[i]
        while i < len(bit_ids) - 1 and bit_ids[i] + 1 == bit_ids[i + 1]:
            i += 1
        high = bit_ids[i]
        if low == high:
            groups.append(str(low))
        elif low + 1 == high:
            groups.append(f"{low},{high}")
        else:
            groups.append(f"{low}-{high}")
        i += 1
    return ",".join(groups)


def human_readable(value: float, order: int = 1000) -> str:
    units = ("K", "M", "G", "T", "P")
    i = 0
    unit = ""
    while value >= order and i < len(units):
        unit = units[i]
        value /= order
        i += 1
    if unit == "":
        return str(value)
    if order == 1024:
        unit += "i"
    if value < 100 and value % 1 > 0:
        return f"{value:.1f}{unit}"
    return f"{value:.0f}{unit}"
