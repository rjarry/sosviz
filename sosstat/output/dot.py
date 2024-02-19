# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry


import contextlib
import os
import re
import secrets

import graphviz

from ..bits import bit_list, human_readable
from ..collect import D


def render(report: D, **opts):
    graph = SOSGraph()
    graph.build(report)
    print(graph.source())


class SOSGraph:

    def __init__(self):
        self.dot = graphviz.Graph(
            name="sosstat",
            node_attr={
                "fontsize": "11",
                "fontname": "monospace",
                "margin": "0.05",
                "shape": "rectangle",
            },
            edge_attr={
                "fontsize": "11",
                "fontname": "monospace",
                "margin": "0",
            },
            graph_attr={
                "fontsize": "11",
                "fontname": "monospace",
                "compound": "true",
                "rankdir": "LR",
            },
        )
        self.cur = self.dot
        self.stack = []
        self.links = []

    def source(self):
        return self.dot.source

    def add_edge(self, a, b, **kwargs):
        for x, y, _ in self.links:
            if (a, b) == (x, y) or (b, a) == (x, y):
                # check for duplicate links
                return
        self.links.append((a, b, kwargs))
        self.dot.edge(a, b, **kwargs)

    @contextlib.contextmanager
    def subgraph(self, name=None, **kwargs):
        self.stack.append(self.cur)
        with self.cur.subgraph(name=name, graph_attr=kwargs) as cur:
            try:
                self.cur = cur
                yield cur
            finally:
                self.cur = self.stack.pop()

    def cluster(self, label, **kwargs):
        kwargs["label"] = format_label(label)
        if "style" not in kwargs:
            kwargs["style"] = "dotted"
        kwargs["cluster"] = "true"
        if isinstance(label, list):
            label = label[0]
        name = safe(label) + "_" + secrets.token_hex(8)
        return self.subgraph(name=name, **kwargs)

    def group(self, **kwargs):
        kwargs["cluster"] = "false"
        return self.subgraph(name=None, **kwargs)

    def node(self, name: str, label: str, **kwargs):
        if kwargs.get("shape", "rectangle") != "rectangle":
            kwargs.setdefault("margin", "0")
        if "tooltip" in kwargs:
            kwargs["tooltip"] = format_label(kwargs["tooltip"])
        self.cur.node(name, format_label(label), **kwargs)

    def build(self, report: D):
        label = [
            f"<b>{report.hardware.system}</b>",
            f"<i>linux {report.software.kernel}</i>",
            report.software.redhat_release,
            report.software.rhosp_release,
        ]
        with self.cluster(label):
            # vms
            for vm in report.get("vms", {}).values():
                with self.cluster(vm.name, style="solid"):
                    for i, numa in vm.get("numa", {}).items():
                        with self.cluster(f"numa {i}", style="dotted"):
                            with self.group(rank="source"):
                                self.vm_numa(vm, numa)
                    for iface in vm.get("interfaces", []):
                        self.vm_iface(iface)

            # linux interfaces
            with self.cluster("linux net devices"):
                for iface in report.get("interfaces", D()).values():
                    if iface.get("kind") == "tun" and not iface.get("ip"):
                        continue
                    self.phy_iface(iface)

            # openvswitch
            label = [f"<b>OVS {report.ovs.config.ovs_version}</b>"]
            if report.ovs.config.get("dpdk_initialized"):
                label.append(report.ovs.config.dpdk_version)
                label.append(bit_list(report.ovs.config.dpdk_cores))
            with self.cluster(label, color="green"):
                for br in report.get("ovs", D()).get("bridges", D()).values():
                    self.ovs_bridge(br)
                for port in report.get("ovs", D()).get("ports", D()).values():
                    if port.type in ("internal", "vxlan"):
                        continue
                    if port.type == "patch":
                        self.add_edge(
                            f"ovs_br_{safe(port.bridge)}",
                            f"ovs_br_{safe(report.ovs.ports[port.options.peer].bridge)}",
                            style="dashed",
                            color="green",
                        )
                        continue
                    self.ovs_port(port)

            for numa in report.get("numa", D()).values():
                with self.cluster(f"phy numa {numa.id}"):
                    self.phy_numa(numa)

    def vm_numa(self, vm: D, numa: D):
        self.node(
            f"{safe(vm.name)}_cpus_{numa.id}",
            f"<b>vcpus {bit_list(numa.vcpus)}</b>",
            color="blue",
        )
        self.node(
            f"{safe(vm.name)}_memory_{numa.id}",
            f"<b>memory {human_readable(numa.memory, 1024)}</b>",
            color="red",
        )
        for h in numa.get("host_numa", []):
            self.add_edge(
                f"{safe(vm.name)}_memory_{numa.id}",
                f"memory_{h}",
                style="dashed",
                color="red",
            )

    def vm_iface(self, iface: D) -> str:
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
        self.node(f"vm_iface_{safe(name)}", labels, color="orange")

    def phy_iface(self, iface: D):
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
            self.add_edge(
                f"phy_{safe(iface.name)}",
                f"pci_{safe(iface.device)}",
                style="dashed",
                colo="orange",
            )

        for ip in iface.get("ip", []):
            labels.append(f'<font color="purple">{ip}</font>')

        tooltips = [iface["flags"]]
        if "mac" in iface:
            tooltips.append(f"mac {iface.mac}")
        if "mtu" in iface:
            tooltips.append(f"mtu {iface.mtu}")

        self.node(
            f"phy_{safe(iface.name)}",
            labels,
            color="green",
            tooltip=tooltips,
        )
        if "link" in iface:
            self.add_edge(
                f"phy_{safe(iface.name)}", f"phy_{safe(iface.link)}", style="dashed"
            )
        if "master" in iface:
            self.add_edge(
                f"phy_{safe(iface.master)}",
                f"phy_{safe(iface.name)}",
                style="dashed",
                color="green",
            )

    def ovs_bridge(self, br: D):
        labels = [
            f"<b>{br.name}</b>",
            f"datapath {br.datapath}",
            f"rules {br.of_rules}",
            f"ports {br.ports}",
        ]
        self.node(f"ovs_br_{safe(br.name)}", labels, color="green", shape="diamond")

    def ovs_port(self, port: D):
        labels = [
            f"<b>{port.name}</b>",
        ]
        if port.type == "dpdkvhostuserclient":
            labels.append("type dpdkvhostuser")
            self.add_edge(
                f"vm_iface_{safe(port.name)}",
                f"ovs_port_{safe(port.name)}",
                style="dashed",
                color="orange",
            )
        if port.type == "bond":
            labels.append("type bond")

        self.node(
            f"ovs_port_{safe(port.name)}",
            labels,
            color="green",
            shape="ellipse",
        )
        self.add_edge(f"ovs_port_{safe(port.name)}", f"ovs_br_{safe(port.bridge)}")

        if port.type == "bond":
            for member in port.members.values():
                labels = [
                    f"<b>{member.name}</b>",
                    f"type {member.type}",
                ]
                if member.type == "dpdk":
                    labels.append(f"{member.options.dpdk_devargs}")
                    labels.append(f"n_rxq {member.options.get('n_rxq', 1)}")
                    self.add_edge(
                        f"ovs_port_{safe(member.name)}",
                        f"pci_{safe(member.options.dpdk_devargs)}",
                        style="dashed",
                        color="orange",
                    )
                self.node(
                    f"ovs_port_{safe(member.name)}",
                    labels,
                    color="green",
                    shape="ellipse",
                )
                self.add_edge(
                    f"ovs_port_{safe(port.name)}",
                    f"ovs_port_{safe(member.name)}",
                    style="solid",
                    color="green",
                )

    def phy_numa(self, numa: D):
        with self.group(rank="sink"):
            self.node(
                f"cpus_{numa.id}", f"<b>cpus {bit_list(numa.cpus)}</b>", color="blue"
            )
            labels = [f"<b>memory {human_readable(numa.total_memory, 1024)}</b>"]
            for size, num in numa.get("hugepages", {}).items():
                if not num:
                    continue
                labels.append(f"{human_readable(size, 1024)} hugepages: {num}")

            self.node(f"memory_{numa.id}", labels, color="red")

        for nic in numa.get("pci_nics", {}).values():
            labels = [f"<b>{nic.pci_id}</b>"]
            if "kernel_driver" in nic:
                labels.append(nic.kernel_driver)
            self.node(
                f"pci_{safe(nic.pci_id)}", labels, tooltip=nic.device, color="orange"
            )


def safe(n):
    return re.sub(r"\W", "_", n)


def format_label(lines: list[str]) -> str:
    if isinstance(lines, str):
        lines = [lines]
    if any(l.startswith("<") for l in lines):
        return "<" + "<br/>".join(lines) + ">"
    return "\\n".join(lines)
