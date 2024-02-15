# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from ..bits import parse_cpu_set


PORT_RE = re.compile(
    r"""
    ^\s{8}Port\s(?P<name>.+)\n
        (?:^\s+tag:\s(?P<tag>\d+)\n)?
        (?P<ifaces>(?:^\s+Interface\s.+\n
            ^\s+type:\s.*\n
            (?:^\s+options:\s.*\n)?
        )+)
    """,
    re.VERBOSE | re.MULTILINE,
)
IFACE_RE = re.compile(
    r"""
    ^\s+Interface\s+(?P<name>.+)\n
        ^\s+type:\s+(?P<type>.+)\n
        (?:^\s+options:\s+(?P<options>.+)\n)?
    """,
    re.VERBOSE | re.MULTILINE,
)
RXQ_RE = re.compile(
    r"""
    \s+port:\s+(\S+)
    \s+queue-id:\s+(\d+)
    \s+\(enabled\)
    \s+pmd\susage:\s*(\d+)\s*%
    $
    """,
    re.VERBOSE | re.MULTILINE,
)


def parse_report(path: pathlib.Path, data: dict):
    ovs = {}

    conf = ovs["config"] = {}
    f = path / "sos_commands/openvswitch/ovs-vsctl_-t_5_list_Open_vSwitch"
    if f.is_file():
        ovs_to_dict(f.read_text(), conf)
    if "other_config" in conf and "pmd-cpu-mask" in conf["other_config"]:
        mask = conf["other_config"]["pmd-cpu-mask"]
        if not mask.startswith("0x"):
            mask = "0x" + mask
        conf["dpdk_cores"] = parse_cpu_set(mask)

    bridges = ovs["bridges"] = {}
    ports = ovs["ports"] = {}
    f = path / "sos_commands/openvswitch/ovs-vsctl_-t_5_show"
    if f.is_file():
        for block in re.split(r"^    Bridge ", f.read_text(), flags=re.MULTILINE):
            br_name, block = block.split("\n", 1)
            for match in PORT_RE.finditer(block):
                ifaces = {}
                for m in IFACE_RE.finditer(match.group("ifaces")):
                    name = m.group("name")
                    ifaces[name] = {"name": name, "type": m.group("type")}
                    if m.group("options"):
                        ifaces[m.group("name")]["options"] = cast_value(
                            m.group("options")
                        )
                if not ifaces:
                    continue
                port_name = match.group("name")
                port = {"name": port_name, "bridge": br_name}
                if len(ifaces) > 1:
                    port["type"] = "bond"
                    port["members"] = ifaces
                else:
                    port.update(ifaces[port_name])
                if match.group("tag"):
                    port["tag"] = int(match.group("tag"))

                ports[port_name] = port
                bridges.setdefault(br_name, {"ports": 0})["ports"] += 1

    for name, br in bridges.items():
        f = path / f"sos_commands/openvswitch/ovs-ofctl_dump-flows_{name}"
        if not f.is_file():
            continue
        br["of_rules"] = len(f.read_text().splitlines()) - 1

    pmds = ovs["pmds"] = {}

    f = path / "sos_commands/openvswitch/ovs-appctl_dpif-netdev.pmd-rxq-show"
    if f.is_file():
        for block in re.split(r"^pmd ", f.read_text(), flags=re.MULTILINE):
            match = re.search(r"thread numa_id (\d+) core_id (\d+):", block)
            if not match:
                continue
            numa, core = match.groups()
            core = int(core)
            numa = int(numa)
            pmds[core] = {"numa": numa, "core": core, "rxqs": []}

            match = re.search(r"isolated\s*:\s*(true|false)", block)
            if match:
                pmds[core]["isolated"] = match.group(1) == "true"

            for match in RXQ_RE.finditer(block):
                port, rxq, usage = match.groups()
                pmds[core]["rxqs"].append(
                    {
                        "port": port,
                        "rxq": int(rxq),
                        "usage": int(usage),
                    }
                )

    data["ovs"] = ovs


PROP_RE = re.compile(r"^([\w-]+)\s*:\s*(.*)$", re.MULTILINE)


def ovs_to_dict(block: str, d: dict):
    for match in PROP_RE.finditer(block):
        key, value = match.groups()
        value = cast_value(value)
        if value in ("", [], {}):
            continue
        d[key] = value


def cast_value(value: str):
    value = value.strip("\t\n\r ")
    if value.startswith("["):
        data = []
        for token in value.strip("[]").split(", "):
            if token.strip() != "":
                data.append(cast_value(token))
        return data
    if value.startswith("{"):
        data = {}
        for token in value.strip("{}").split(", "):
            if token.strip() != "":
                try:
                    key, val = token.split("=", 1)
                except ValueError:
                    continue
                data[key.strip()] = cast_value(val)
        return data
    if value.strip('"') == "true":
        return True
    if value.strip('"') == "false":
        return False
    if value.isdigit():
        return int(value)
    return value.strip('"')
