# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D


IFACE_RE = re.compile(
    r"""
    ^(?P<name>[^@:]+?)(?:@(?P<link>[^:]+))?:\s+
        <(?P<flags>[\w,-]+)>\s+
        mtu\s+(?P<mtu>\d+)(?:\s+(?:qdisc|mq))*
        (?:\s+master\s+(?P<master>\S+)\s)?.*\n
    ^\s+link/ether\s+(?P<mac>[a-f\d:]+)\s.*\n
    (?:^\s+
        (?P<kind>\S+)\s+
        (?:
            protocol\s+\S+\s+id\s+(?P<vlan>\d+)
            |
            type\s+(?P<tun_type>\S+)
            |
            mode\s+(?P<bond_mode>\S+)
            |
            state\s+(?P<slave_state>\S+)
        )\s.*
    \n)?
    """,
    re.VERBOSE | re.MULTILINE,
)
ADDR_RE = re.compile(
    r"inet6? (?P<addr>(?:\d+(?:\.\d+){3}|[a-f\d:]+)/\d+) .*scope global",
)


def parse_report(path: pathlib.Path, data: D):
    data.interfaces = ip = D()
    f = path / "sos_commands/networking/ip_-d_address"
    if not f.is_file():
        return
    for block in re.split(r"^\d+: ", f.read_text(), flags=re.MULTILINE):
        match = IFACE_RE.search(block)
        if not match:
            continue
        d = D({k: v for (k, v) in match.groupdict().items() if v is not None})
        for dev in path.glob(f"sys/class/net/{d.name}/device"):
            d.device = dev.resolve().name
        ip[d.name] = d
        for m in ADDR_RE.finditer(block):
            d.setdefault("ip", []).append(m.group("addr"))
