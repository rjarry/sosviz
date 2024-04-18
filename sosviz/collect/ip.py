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
    stats = get_netdev_stats(path)
    data.interfaces = parse_interfaces(
        path / "sos_commands/networking/ip_-d_address", path, stats
    )
    data.netns = D()
    for ip_addr in path.glob(
        "sos_commands/networking/namespaces/*/*_ip_-d_address_show"
    ):
        netns = re.sub(r"ip_netns_exec_(.*)_ip_-d_address_show", r"\1", ip_addr.name)
        data.netns[ip_addr.parent.name] = parse_interfaces(ip_addr, path, D())
    for ip_addr in path.glob(
        "sos_commands/networking/ip_netns_exec_*_ip*_address_show"
    ):
        netns = re.sub(r"ip_netns_exec_(.*)_ip.*_address_show", r"\1", ip_addr.name)
        data.netns[netns] = parse_interfaces(ip_addr, path, D())


def parse_interfaces(ip_addr: pathlib.Path, path: pathlib.Path, stats: D) -> D:
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
        if d.name in stats:
            d.stats = stats[d.name]
    return ifaces


STATS_RE = re.compile(
    r"""
    ^
    \s*
    (?P<name>[^:]+):\s+
    (?P<rx_bytes>\d+)\s+
    (?P<rx_packets>\d+)\s+
    (?P<rx_errors>\d+)\s+
    (?P<rx_dropped>\d+)\s+
    (?P<rx_fifo>\d+)\s+
    (?P<rx_frame>\d+)\s+
    (?P<rx_compressed>\d+)\s+
    (?P<rx_multicast>\d+)\s+
    (?P<tx_bytes>\d+)\s+
    (?P<tx_packets>\d+)\s+
    (?P<tx_errors>\d+)\s+
    (?P<tx_dropped>\d+)\s+
    (?P<tx_fifo>\d+)\s+
    (?P<tx_colls>\d+)\s+
    (?P<tx_carrier>\d+)\s+
    (?P<tx_compressed>\d+)
    \s*
    $
    """,
    re.VERBOSE | re.MULTILINE,
)


def get_netdev_stats(path: pathlib.Path) -> D:
    stats = D()
    dev = path / "proc/net/dev"
    if not dev.is_file():
        return stats

    for match in STATS_RE.finditer(dev.read_text()):
        dic = match.groupdict()
        name = dic.pop("name")
        stats[name] = D({k: int(v) for k, v in dic.items()})

    return stats
