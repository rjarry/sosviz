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
    print(SOSGraph(report).source())


class SOSGraph:

    def __init__(self, report: D):
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
        self.links = set()
        self.report = report
        self.build()

    def source(self):
        return self.dot.source

    def edge(self, a, b, force=False, **kwargs):
        link = frozenset((a, b))
        if link in self.links and not force:
            # check for duplicate links
            return
        self.links.add(link)
        if "label" in kwargs:
            kwargs["label"] = format_label(kwargs["label"])
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

    def build(self):
        r = self.report
        label = [
            f"<b>{r.hardware.system}</b>",
            f"<i>linux {r.software.kernel}</i>",
            r.software.redhat_release,
            r.software.rhosp_release,
        ]
        with self.cluster(label):
            # vms
            for vm in r.get("vms", {}).values():
                with self.cluster(f"VM {vm.name}", style="solid"):
                    for i, numa in vm.get("numa", {}).items():
                        with self.cluster(f"numa {i}", style="dotted"):
                            with self.group(rank="source"):
                                self.vm_numa(vm, numa)
                    for iface in vm.get("interfaces", []):
                        self.vm_iface(iface)

            # linux interfaces
            with self.cluster("linux net devices"):
                for iface in r.get("interfaces", D()).values():
                    self.phy_iface(iface)

            # openvswitch
            label = [f"<b>OVS {r.ovs.config.ovs_version}</b>"]
            if r.ovs.config.get("dpdk_initialized"):
                label.append(r.ovs.config.dpdk_version)
            with self.cluster(label, color="green"):
                for br in r.get("ovs", D()).get("bridges", D()).values():
                    self.ovs_bridge(br)
                for port in r.get("ovs", D()).get("ports", D()).values():
                    if port.type in ("internal", "vxlan"):
                        continue
                    if port.type == "patch":
                        self.edge(
                            f"ovs_br_{safe(port.bridge)}",
                            f"ovs_br_{safe(r.ovs.ports[port.options.peer].bridge)}",
                            style="dashed",
                            color="green",
                        )
                        continue
                    self.ovs_port(port)
                self.ovs_pmds(r.ovs)

            # physical CPU/memory
            for numa in r.get("numa", D()).values():
                with self.cluster(f"phy numa {numa.id}"):
                    self.phy_numa(numa)

    def vm_numa(self, vm: D, numa: D):
        labels = [f"<b>vCPUs {bit_list(numa.vcpus)}</b>"]
        host_cpus = set()
        for vcpu in numa.vcpus:
            host_cpus.update(vm.vcpu_pinning[vcpu])
        labels.append(f"host CPUs {bit_list(host_cpus)}")
        cpu_numas = set()
        for n in self.report.numa.values():
            if host_cpus & n.cpus:
                cpu_numas.add(n.id)
        labels.append(f"host NUMA {bit_list(cpu_numas)}")
        self.node(f"{safe(vm.name)}_cpus_{numa.id}", labels, color="blue")

        labels = [f"<b>memory {human_readable(numa.memory, 1024)}</b>"]
        for h in numa.get("host_numa", []):
            labels.append(f"host NUMA {h}")
        self.node(f"{safe(vm.name)}_memory_{numa.id}", labels, color="red")

    def vm_iface(self, iface: D) -> str:
        labels = [f"<b>{iface.type}</b>"]
        name = None
        peer = None
        if "socket" in iface:
            name = os.path.basename(iface.socket)
            peer = f"ovs_port_{safe(name)}"
        elif "host_dev" in iface:
            name = iface.host_dev
            peer = f"pci_{safe(name)}"
        elif "net_dev" in iface:
            name = iface.net_dev
            peer = f"phy_{safe(name)}"
        if name:
            labels.append(name)
        if "vlan" in iface:
            labels.append(f"VLAN {iface.vlan}")
        if "bridge" in iface:
            labels.append(f"<i>bridge {iface.bridge}</i>")
        if "queues" in iface:
            labels.append(f"<i>queues {iface.queues}</i>")
        self.node(f"vm_iface_{safe(name)}", labels, color="orange")
        if peer:
            self.edge(f"vm_iface_{safe(name)}", peer, style="dashed", color="orange")

    def phy_iface(self, iface: D):
        labels = [f"<b>{iface.name}</b>"]

        kind = iface.get("kind")
        if kind == "bond" and "bond_mode" in iface:
            kind += f" {iface.bond_mode}"
        if kind == "vlan" and "vlan" in iface:
            kind += f" {iface.vlan}"
        if kind == "tun" and "tun_type" in iface:
            kind += f" {iface.tun_type}"
        if kind:
            labels.append(kind)
        if "device" in iface:
            labels.append(iface.device)
            self.edge(
                f"phy_{safe(iface.name)}",
                f"pci_{safe(iface.device)}",
                style="dashed",
                color="orange",
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
            self.edge(
                f"phy_{safe(iface.name)}",
                f"phy_{safe(iface.link)}",
                style="dashed",
                color="green",
            )
        if "master" in iface:
            self.edge(
                f"phy_{safe(iface.master)}",
                f"phy_{safe(iface.name)}",
                style="solid",
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
        if port.type == "bond":
            labels.append("type bond")

        if "tag" in port:
            labels.append(f'<font color="green">VLAN {port.tag}</font>')

        self.node(
            f"ovs_port_{safe(port.name)}",
            labels,
            color="green",
            shape="ellipse",
        )
        self.edge(f"ovs_port_{safe(port.name)}", f"ovs_br_{safe(port.bridge)}")

        if port.type == "bond":
            for member in port.members.values():
                labels = [
                    f"<b>{member.name}</b>",
                    f"type {member.type}",
                ]
                if member.type == "dpdk":
                    labels.append(f"{member.options.dpdk_devargs}")
                    labels.append(f"n_rxq {member.options.get('n_rxq', 1)}")
                    self.edge(
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
                self.edge(
                    f"ovs_port_{safe(port.name)}",
                    f"ovs_port_{safe(member.name)}",
                    style="solid",
                    color="green",
                )

    BLUES = (
        "cornflowerblue",
        "dodgerblue",
        "mediumturquoise",
        "deepskyblue",
        "steelblue",
        "navy",
        "turquoise",
        "darkslateblue",
        "darkcyan",
    )

    def ovs_pmds(self, ovs: D):
        with self.cluster("DPDK PMD cores", style="dotted", color="blue", rank="sink"):
            for pmd in ovs.pmds.values():
                color = self.BLUES[pmd.core % len(self.BLUES)]
                self.node(
                    f"ovs_pmd_{pmd.core}",
                    f"<b>Core {pmd.core} NUMA {pmd.numa}</b>",
                    color=color,
                )
                for rxq in pmd.rxqs:
                    self.edge(
                        f"ovs_pmd_{pmd.core}",
                        f"ovs_port_{safe(rxq.port)}",
                        force=True,
                        style="bold",
                        color=color,
                    )

    def irq_counters_tooltip(self, cpus: set[int]) -> str:
        tooltip = []
        for c in cpus:
            counter = 0
            bound = 0
            for irq in self.report.irqs.values():
                if not irq.irq.isdigit():
                    continue
                if c in irq.get("effective_affinity", []):
                    bound += 1
                counter += irq.counters[c]
            if counter < 42:  # XXX: how about 1337 maybe?
                continue
            tooltip.append(f"CPU {c} bound_irqs={bound} interrupts={counter}")
        return format_label(tooltip)

    def phy_numa(self, numa: D):
        model = "<b>Unknown Processor Model</b>"
        for i, proc in enumerate(self.report.hardware.processor):
            if i == numa.id:
                model = f"<b>{proc.model}</b>"
        with self.cluster(model, style="dotted", color="blue"):
            housekeeping_cpus = set(numa.cpus)

            ovs_cpus = set()
            for pmd in self.report.ovs.pmds.values():
                if pmd.numa != numa.id:
                    continue
                ovs_cpus.add(pmd.core)
            self.node(
                f"phy_cpus_ovs_{numa.id}",
                ["<b>OVS DPDK</b>", f"CPUs {bit_list(ovs_cpus)}"],
                tooltip=self.irq_counters_tooltip(ovs_cpus),
                color="blue",
            )
            housekeeping_cpus -= ovs_cpus

            for vm in self.report.get("vms", {}).values():
                for vnuma in vm.numa.values():
                    if numa.id not in vnuma.host_numa:
                        continue
                    host_cpus = set()
                    for vcpu in vnuma.vcpus:
                        host_cpus.update(vm.vcpu_pinning[vcpu])
                    self.node(
                        f"phy_cpus_{safe(vm.name)}_{numa.id}",
                        [f"<b>VM {vm.name}</b>", f"CPUs {bit_list(host_cpus)}"],
                        tooltip=self.irq_counters_tooltip(host_cpus),
                        color="blue",
                    )
                    housekeeping_cpus -= host_cpus

            self.node(
                f"phy_cpus_housekeeping_{numa.id}",
                ["<b>Housekeeping</b>", f"CPUs {bit_list(housekeeping_cpus)}"],
                tooltip=self.irq_counters_tooltip(housekeeping_cpus),
                color="blue",
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
