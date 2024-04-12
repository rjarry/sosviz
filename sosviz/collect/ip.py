# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D


IFACE_RE = re.compile(
    r"""
    ^(?P<index>\d+):\s+(?P<name>[^@:]+?)(?:@(?P<link>[^:]+))?:\s+
        <(?P<flags>[\w,-]+)>\s+
        mtu\s+(?P<mtu>\d+)
        (?:.*?\smaster\s+(?P<master>\S+)\s)?.*\n
    ^\s+link/ether\s+(?P<mac>[a-f\d:]+)\sbrd\s[a-f\d:]+
        (?:\s+link-netns(?:id)?\s+(?P<link_netns>\S+))?\s.*\n
    (?:^\s+
        (?P<kind>
            vlan
            |
            bridge
            |
            bond
            |
            veth
            |
            vxlan
            |
            tun
            |
            bond_slave
            |
            bridge_slave
        )\s+
        (?:
            protocol\s+\S+\s+id\s+(?P<vlan>\d+)
            |
            type\s+(?P<tun_type>\S+)
            |
            mode\s+(?P<bond_mode>\S+)
            |
            state\s+(?P<slave_state>\S+)
        )?.*
    \n)?
    """,
    re.VERBOSE | re.MULTILINE,
)
ADDR_RE = re.compile(
    r"inet6? (?P<addr>(?:\d+(?:\.\d+){3}|[a-f\d:]+)/\d+) .*scope global",
)
IFACE_BLOCK_RE = re.compile(r"^\d+:\s.*\n(\s{4}.+\n)+", re.VERBOSE | re.MULTILINE)


def parse_report(path: pathlib.Path, data: D):
    data.interfaces = parse_interfaces(
        path / "sos_commands/networking/ip_-d_address", path
    )
    data.netns = D()
    for netns in path.glob("sos_commands/networking/namespaces/*/*_ip_-d_address_show"):
        data.netns[netns.parent.name] = parse_interfaces(netns, path)


def parse_interfaces(ip_addr: pathlib.Path, path: pathlib.Path) -> D:
    ifaces = D()
    if not ip_addr.is_file():
        return ifaces
    for block in IFACE_BLOCK_RE.finditer(ip_addr.read_text()):
        match = IFACE_RE.search(block.group())
        if not match:
            continue
        d = D({k: v for (k, v) in match.groupdict().items() if v is not None})
        for dev in path.glob(f"sys/class/net/{d.name}/device"):
            d.device = dev.resolve().name
        ifaces[d.name] = d
        for m in ADDR_RE.finditer(block.group()):
            d.setdefault("ip", []).append(m.group("addr"))
    return ifaces
