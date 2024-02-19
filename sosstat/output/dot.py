# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry


import os
import re

from ..bits import bit_list, human_readable
from ..collect import D


def render(report: D, **opts):
    print("graph {")
    print("  node [fontsize=11 fontname=monospace margin=0.05 shape=rectangle];")
    print("  edge [fontsize=11 fontname=monospace margin=0];")
    print("  graph [fontsize=11 fontname=monospace compound=true style=dotted];")

    links = set()
    for vm in report.get("vms", {}).values():
        print(f"  subgraph cluster_{safe(vm.name)} {{")
        print(f'    label="vm {vm.name}";')
        print("    style=solid;")
        for i, numa in vm.get("numa", {}).items():
            print(f"    subgraph cluster_{safe(vm.name)}_numa{i} {{")
            print(f'      label="numa {i}";')
            print("      style=dotted;")
            print("{")
            print("   cluster=false;")
            print("   rank=source;")
            print_vm_cpu(vm, numa)
            print_vm_memory(vm, numa)
            for h in numa.get("host_numa", []):
                add_link(
                    links, f"{safe(vm.name)}_memory_{i}", f"memory_{h}", "dashed", "red"
                )
            print("    }")
            print("    }")
        for iface in vm.get("interfaces", []):
            print_vm_iface(iface)
        print("  }")

    print("subgraph cluster_interfaces {")
    for iface in report.get("interfaces", D()).values():
        if iface.get("kind") == "tun" and not iface.get("ip"):
            continue
        print_phy_iface(iface, links)
    print("}")

    print("subgraph cluster_ovs {")
    print(f'      label="OVS {report.ovs.config.ovs_version}"')
    if report.ovs.get("dpdk_initialized"):
        print(
            f'      label="{report.ovs.config.dpdk_version}"\\n'
            f'\\npmd-cpus={bit_list(report.ovs.config.dpdk_cores)}"'
        )
    for br in report.get("ovs", D()).get("bridges", D()).values():
        print_ovs_bridge(br)

    for port in report.get("ovs", D()).get("ports", D()).values():
        if port.type in ("internal", "vxlan"):
            continue
        if port.type == "patch":
            add_link(
                links,
                f"ovs_br_{safe(port.bridge)}",
                f"ovs_br_{safe(report.ovs.ports[port.options.peer].bridge)}",
                "dashed",
                "green",
            )
            continue
        print_ovs_port(port, links)
    print("}")

    for i, numa in report.get("numa", {}).items():
        print(f"    subgraph cluster_numa_{i} {{")
        print(f'      label="numa {i}"')

        print("{")
        print("   cluster=false;")
        print("   rank=sink;")

        print(f"      {cpu(numa)}")
        print(f"      {memory(numa)}")
        print("    }")

        print("      {")
        for nic in numa.get("pci_nics", {}).values():
            print(f"        {pci_nic(nic)}")
        print("      }")
        print("    }")

    for a, b, style, color in links:
        attrs = {}
        if style is not None:
            attrs["style"] = style
        if color is not None:
            attrs["color"] = color
        if attrs:
            attrs = f" [{' '.join(f'{k}={v}' for k, v in attrs.items())}]"
        print(f"    {a} -- {b}{attrs}")

    print("}")


def ovs_label(config: D) -> str:
    labels = [f"OVS {config.ovs_version}"]
    if "dpdk_version" in config:
        labels.append(config.dpdk_version)
    return "\\n".join(labels)


def print_ovs_bridge(br: D) -> str:
    labels = [
        f"<b>{br.name}</b>",
        f"datapath {br.datapath}",
        f"of rules {br.of_rules}",
        f"ports {br.ports}",
    ]
    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "green",
        "shape": "diamond",
    }
    print(dot_node(f"ovs_br_{safe(br.name)}", attrs))


def print_ovs_port(port: D, links: set) -> str:
    labels = [
        f"<b>{port.name}</b>",
    ]
    if port.type == "dpdkvhostuserclient":
        labels.append("type dpdk vhost-user")
        add_link(
            links,
            f"vm_iface_{safe(port.name)}",
            f"ovs_port_{safe(port.name)}",
            "dashed",
            "orange",
        )
    if port.type == "bond":
        labels.append("type bond")

    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "green",
        "shape": "ellipse",
    }
    print(dot_node(f"ovs_port_{safe(port.name)}", attrs))
    add_link(links, f"ovs_port_{safe(port.name)}", f"ovs_br_{safe(port.bridge)}")

    if port.type == "bond":
        for member in port.members.values():
            labels = [
                f"<b>{port.name}</b>",
                f"type {port.type}",
            ]
            if member.type == "dpdk":
                labels.append(f"{member.options.dpdk_devargs}")
                labels.append(f"n_rxq {member.options.get('n_rxq', 1)}")
                add_link(
                    links,
                    f"ovs_port_{safe(member.name)}",
                    f"pci_{safe(member.options.dpdk_devargs)}",
                    "dashed",
                    "orange",
                )

            attrs = {
                "label": f"<{'<br/>'.join(labels)}>",
                "color": "green",
                "shape": "ellipse",
            }
            print(dot_node(f"ovs_port_{safe(member.name)}", attrs))
            add_link(
                links,
                f"ovs_port_{safe(port.name)}",
                f"ovs_port_{safe(member.name)}",
                "solid",
                "green",
            )


def software_label(sw: D) -> str:
    labels = [sw.kernel]
    if "redhat_release" in sw:
        labels.append(sw.redhat_release)
    if "rhosp_release" in sw:
        labels.append(sw.rhosp_release)
    return f"<{'<br/>'.join(labels)}>"


def cpu(numa: D) -> str:
    labels = [
        f"<b>cpus {bit_list(numa.cpus)}</b>",
    ]
    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "blue",
    }
    return dot_node(f"cpus_{numa.id}", attrs)


def memory(numa: D) -> str:
    labels = [f"<b>memory {human_readable(numa.total_memory, 1024)}</b>"]

    for size, num in numa.get("hugepages", {}).items():
        if not num:
            continue
        labels.append(f"{human_readable(size, 1024)} hugepages: {num}")
    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "red",
    }
    return dot_node(f"memory_{numa.id}", attrs)


def pci_nic(nic: D) -> str:
    labels = [f"<b>{nic.pci_id}</b>"]
    if "kernel_driver" in nic:
        labels.append(nic.kernel_driver)
    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "orange",
        "tooltip": '"' + nic.device + '"',
    }
    return dot_node(f"pci_{safe(nic.pci_id)}", attrs)


def print_phy_iface(iface: D, links: set) -> str:
    labels = [f"<b>{iface.name}</b>"]

    kind = iface.get("kind")
    if kind == "bond":
        labels.append(f"bond {iface.bond_mode}")
    if kind == "vlan":
        labels.append(f"vlan {iface.vlan}")
    if kind == "tun":
        labels.append(f"tun {iface.tun_type}")
    if "device" in iface:
        labels.append(iface.device)
        add_link(
            links,
            f"phy_{safe(iface.name)}",
            f"pci_{safe(iface.device)}",
            "dashed",
            "orange",
        )

    for ip in iface.get("ip", []):
        labels.append(f'<font color="purple">{ip}</font>')

    tooltips = [iface["flags"]]
    if "mac" in iface:
        tooltips.append(f"mac {iface.mac}")
    if "mtu" in iface:
        tooltips.append(f"mtu {iface.mtu}")

    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "green",
        "tooltip": '"' + "\\n".join(tooltips) + '"',
    }
    print(dot_node(f"phy_{safe(iface.name)}", attrs))
    if "link" in iface:
        add_link(links, f"phy_{safe(iface.name)}", f"phy_{safe(iface.link)}", "dashed")
    if "master" in iface:
        add_link(
            links,
            f"phy_{safe(iface.master)}",
            f"phy_{safe(iface.name)}",
            "solid",
            "green",
        )


def print_vm_cpu(vm: D, numa: D) -> str:
    labels = [
        f"<b>vcpus {bit_list(numa.vcpus)}</b>",
    ]
    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "blue",
    }
    print(dot_node(f"{safe(vm.name)}_cpus_{numa.id}", attrs))


def print_vm_memory(vm: D, numa: D) -> str:
    labels = [f"<b>memory {human_readable(numa.memory, 1024)}</b>"]
    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "red",
    }
    print(dot_node(f"{safe(vm.name)}_memory_{numa.id}", attrs))


def print_vm_iface(iface: D) -> str:
    labels = [f"<b>{iface.type}</b>"]
    name = "unset"
    if "socket" in iface:
        name = os.path.basename(iface.socket)
    elif "host_dev" in iface:
        name = iface.host_dev
    labels.append(name)
    if "bridge" in iface:
        labels.append(f"<i>bridge {iface.bridge}</i>")
    if "queues" in iface:
        labels.append(f"<i>queues {iface.queues}</i>")
    attrs = {
        "label": f"<{'<br/>'.join(labels)}>",
        "color": "orange",
    }
    print(dot_node(f"vm_iface_{safe(name)}", attrs))


def dot_node(name: str, attrs: D) -> str:
    if attrs.get("shape", "rectangle") != "rectangle":
        attrs.setdefault("margin", "0")
    return f"{name} [{' '.join(f'{k}={v}' for k, v in attrs.items())}]"


def safe(n):
    return re.sub(r"\W", "_", n)


def add_link(links: set, a: str, b: str, style=None, color=None):
    for x, y, s, c in links:
        if (a, b) == (x, y) or (b, a) == (x, y):
            return
    links.add((a, b, style, color))
