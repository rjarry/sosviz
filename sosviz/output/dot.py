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
            name="sosviz",
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
        self.clusters = set()
        self.report = report
        self.build()

    def source(self):
        return self.dot.source

    def safe_id(self, n):
        return re.sub(r"\W", "_", n)

    def edge(self, a, b, force=False, **kwargs):
        a = self.safe_id(a)
        b = self.safe_id(b)
        link = frozenset((a, b))
        if link in self.links and not force:
            # check for duplicate links
            return
        self.links.add(link)
        if "label" in kwargs:
            kwargs["label"] = format_label(kwargs["label"], max_width=30)
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
        name = self.safe_id(label)
        if name in self.clusters:
            name += secrets.token_hex(8)
        self.clusters.add(name)
        return self.subgraph(name=name, **kwargs)

    def group(self, **kwargs):
        kwargs["cluster"] = "false"
        return self.subgraph(name=None, **kwargs)

    def node(self, name: str, label: str, **kwargs):
        name = self.safe_id(name)
        if kwargs.get("shape", "rectangle") != "rectangle":
            kwargs.setdefault("margin", "0")
        if "tooltip" in kwargs:
            kwargs["tooltip"] = format_label(kwargs["tooltip"])
        self.cur.node(name, format_label(label, max_width=30), **kwargs)

    def build(self):
        r = self.report
        label = [
            f"<b>{r.hostname} / <i>{r.hardware.system}</i></b>",
            f"<i>linux {r.software.kernel}</i>",
        ]
        for sw in "os_release", "rhosp_release":
            if sw in r.software:
                label.append(r.software.get(sw))

        if "ovs" in r:
            ovs = f"OVS {r.ovs.config.ovs_version}"
            if r.ovs.config.get("dpdk_initialized"):
                ovs += f" {r.ovs.config.dpdk_version}"
            label.append(ovs)

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
            with self.cluster("networking"):
                # openvswitch
                for br in r.get("ovs", D()).get("bridges", D()).values():
                    self.ovs_bridge(br)
                for port in r.get("ovs", D()).get("ports", D()).values():
                    if port.type in ("vxlan", "geneve", "internal", ""):
                        continue
                    if port.type == "patch":
                        self.edge(
                            self.ovs_br_node_id(port.bridge),
                            self.ovs_br_node_id(r.ovs.ports[port.options.peer].bridge),
                            style="dashed",
                            color="forestgreen",
                        )
                        continue
                    self.ovs_port(port)

                # linux networking
                for iface in r.get("interfaces", D()).values():
                    self.phy_iface(iface, netns="")

                for netns, ifaces in r.netns.items():
                    with self.cluster(f"netns {netns}", color="salmon", style="dashed"):
                        for iface in ifaces.values():
                            self.phy_iface(iface, netns=netns)

            # physical CPU/memory
            for numa in r.get("numa", D()).values():
                with self.cluster(f"phy numa {numa.id}"):
                    self.phy_numa(numa)

    def vm_cpu_node_id(self, vm, numa):
        return f"{vm.name}_cpu_{numa.id}"

    def vm_memory_node_id(self, vm, numa):
        return f"{vm.name}_memory_{numa.id}"

    def vm_numa(self, vm: D, numa: D):
        labels = [f"<b>vCPUs {bit_list(numa.vcpus)}</b>"]
        host_cpus = set()
        for vcpu in numa.vcpus:
            host_cpus.update(vm.vcpu_pinning.get(vcpu, set()))
        if host_cpus:
            labels.append(f"host CPUs {bit_list(host_cpus)}")
        cpu_numas = set()
        for n in self.report.numa.values():
            if host_cpus & n.cpus:
                cpu_numas.add(n.id)
        if cpu_numas:
            labels.append(f'<font color="blue">host NUMA {bit_list(cpu_numas)}</font>')
        self.node(self.vm_cpu_node_id(vm, numa), labels, color="blue")

        labels = [f"<b>memory {human_readable(numa.memory, 1024)}</b>"]
        for h in numa.get("host_numa", []):
            labels.append(f'<font color="red">host NUMA {h}</font>')
        self.node(self.vm_memory_node_id(vm, numa), labels, color="red")

    def vm_iface_node_id(self, name):
        return f"vm_iface_{name}"

    def vm_iface(self, iface: D) -> str:
        labels = [f"<b>{iface.type}</b>"]
        name = None
        peer = None
        color = "darkorange"
        if "socket" in iface:
            color = "forestgreen"
            name = os.path.basename(iface.socket)
            peer = self.ovs_port_node_id(name)
        elif "host_dev" in iface:
            color = "darkorange"
            name = iface.host_dev
            peer = pci_node_id(iface.host_dev)
        elif "net_dev" in iface:
            color = "hotpink"
            name = iface.net_dev
            peer = self.iface_node_id(iface.net_dev, "")
        if name:
            labels.append(name)
        if "vlan" in iface:
            labels.append(f"VLAN {iface.vlan}")
        if "bridge" in iface:
            labels.append(f"<i>bridge {iface.bridge}</i>")
        if "queues" in iface:
            labels.append(f"<i>queues {iface.queues}</i>")
        self.node(self.vm_iface_node_id(name), labels, color=color)
        if peer:
            self.edge(self.vm_iface_node_id(name), peer, style="dashed", color=color)

    def iface_node_id(self, name, netns):
        return f"net_{netns}_{name}"

    NETDEV_ERRORS = {
        "rx_dropped",
        "rx_errors",
        "rx_fifo",
        "rx_frame",
        "tx_carrier",
        "tx_colls",
        "tx_dropped",
        "tx_errors",
        "tx_fifo",
    }

    def phy_iface(self, iface: D, netns: str = ""):
        if netns == "" and iface.name in self.report.ovs.bridges:
            return
        if iface.name in "ovs-system" or re.match(r"(genev|vxlan)_sys_\d+", iface.name):
            return

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
                self.iface_node_id(iface.name, netns),
                pci_node_id(iface.device),
                style="dashed",
                color="darkorange",
            )

        for ip in iface.get("ip", []):
            labels.append(f'<font color="purple">{ip}</font>')

        tooltips = [iface["flags"]]
        if "mac" in iface:
            tooltips.append(f"mac {iface.mac}")
        if "mtu" in iface:
            tooltips.append(f"mtu {iface.mtu}")

        state = []
        if "DOWN" in iface["flags"]:
            state.append('<font color="darkorange">DOWN</font>')
        else:
            state.append('<font color="forestgreen">UP</font>')
        if "NO-CARRIER" in iface["flags"]:
            state.append('<font color="red">NO-CARRIER</font>')
        elif "LOWER_UP" in iface["flags"]:
            state.append('<font color="forestgreen">LOWER_UP</font>')
        labels.append(f"state {','.join(state)}")

        for name, value in iface.get("stats", {}).items():
            tooltips.append(f"{name} {human_readable(value)}")
            if value and "LOWER_UP" in iface["flags"] and name in self.NETDEV_ERRORS:
                labels.append(
                    f'<font color="red">{name} {human_readable(value)}</font>'
                )

        color = "salmon" if netns else "hotpink"
        self.node(
            self.iface_node_id(iface.name, netns),
            labels,
            color=color,
            tooltip=tooltips,
        )
        if "link" in iface:
            if "link_netns" in iface:
                link_ns = iface.link_netns
                if link_ns == "0":
                    link_ns = ""
            else:
                link_ns = netns
            link = self.find_iface(iface.link, link_ns)
            self.edge(
                self.iface_node_id(iface.name, netns),
                self.iface_node_id(link.name, link_ns),
                style="dashed",
                color=color,
            )
        if "master" in iface and iface.master != "ovs-system":
            self.edge(
                self.iface_node_id(iface.master, netns),
                self.iface_node_id(iface.name, netns),
                style="solid",
                color=color,
            )
        if iface.name in self.report.ovs.ports:
            port = self.report.ovs.ports[iface.name]
            self.edge(
                self.ovs_br_node_id(port.bridge),
                self.iface_node_id(iface.name, netns),
                style="solid",
                color="forestgreen",
            )

    def find_iface(self, name, netns):
        if netns:
            ifaces = self.report.netns[netns]
        else:
            ifaces = self.report.interfaces
        match = re.match(r"if(\d+)", name)
        if not match:
            return ifaces[name]
        for iface in ifaces.values():
            if iface.index == match.group(1):
                return iface
        raise KeyError(name)

    def ovs_br_node_id(self, name):
        return f"ovs_br_{name}"

    def ovs_bridge(self, br: D):
        labels = [
            f"<b>{br.name}</b>",
            f"OVS {br.datapath}",
            f"rules {br.of_rules}",
            f"ports {br.ports}",
        ]
        iface = self.report.interfaces.get(br.name, None)
        if iface is not None:
            for ip in self.report.interfaces[br.name].get("ip", []):
                labels.append(f'<font color="purple">{ip}</font>')
            if "link" in iface:
                link_ns = ""
                if "link_netns" in iface:
                    link_ns = iface.link_netns
                    if link_ns == "0":
                        link_ns = ""
                link = self.find_iface(iface.link, link_ns)
                self.edge(
                    self.ovs_br_node_id(br.name),
                    self.iface_node_id(link.name, link_ns),
                    style="dashed",
                    color="forestgreen",
                )
            if "master" in iface:
                self.edge(
                    self.iface_node_id(iface.master, ""),
                    self.ovs_br_node_id(br.name),
                    style="solid",
                    color="forestgreen",
                )
        self.node(
            self.ovs_br_node_id(br.name), labels, color="forestgreen", shape="diamond"
        )
        vxlan_ports = 0
        geneve_ports = 0
        for port in self.report.ovs.ports.values():
            if port.bridge != br.name:
                continue
            if port.type == "vxlan":
                vxlan_ports += 1
            if port.type == "geneve":
                geneve_ports += 1
        if vxlan_ports > 0:
            vxlan_stub = self.ovs_br_node_id(br.name) + "_vxlans"
            self.node(
                vxlan_stub,
                f"{vxlan_ports} VXLAN ports",
                shape="ellipse",
                color="forestgreen",
                style="dashed",
            )
            self.edge(
                vxlan_stub,
                self.ovs_br_node_id(br.name),
                color="forestgreen",
                style="solid",
            )
        if geneve_ports > 0:
            geneve_stub = self.ovs_br_node_id(br.name) + "_geneves"
            self.node(
                geneve_stub,
                f"{geneve_ports} GENEVE ports",
                shape="ellipse",
                color="forestgreen",
                style="dashed",
            )
            self.edge(
                geneve_stub,
                self.ovs_br_node_id(br.name),
                color="forestgreen",
                style="solid",
            )

    def ovs_port_node_id(self, name):
        return f"ovs_port_{name}"

    def ovs_port_state(self, state: str) -> str:
        if state == "up":
            return '<font color="forestgreen">up</font>'
        return '<font color="red">DOWN</font>'

    def ovs_base_labels(self, port: D):
        labels = [
            f"<b>{port.name}</b>",
            f"OVS {port.type}",
        ]
        if "admin_state" in port and "link_state" in port:
            state = ",".join(
                self.ovs_port_state(s) for s in (port.admin_state, port.link_state)
            )
            labels.append(f"state {state}")
        if "tag" in port:
            labels.append(f'<font color="forestgreen">VLAN {port.tag}</font>')
        return labels

    def ovs_dpdk_labels(self, port: D):
        if "dpdk_devargs" in port.options:
            numa_id = "N/A"
            for numa in self.report.numa.values():
                if port.options.dpdk_devargs in numa.pci_nics:
                    numa_id = numa.id
                    break
            yield f"{port.options.dpdk_devargs} NUMA {numa_id}"

        disabled = set()
        rxqs = []
        for pmd in self.report.ovs.pmds.values():
            for rxq in pmd.rxqs:
                if rxq.port == port.name:
                    if rxq.enabled:
                        rxqs.append((rxq.rxq, pmd.core, pmd.numa))
                    else:
                        disabled.add(rxq.rxq)

        for rxq, core, numa in sorted(rxqs):
            yield f"rxq {rxq} cpu {core} NUMA {numa}"
        if disabled:
            s = "s" if len(disabled) > 1 else ""
            yield f'<font color="gray">rxq{s} {bit_list(disabled)} disabled</font>'

    OVS_ERRORS = {
        "collisions",
        "ovs_rx_qos_drops",
        "ovs_tx_failure_drops",
        "ovs_tx_invalid_hwol_drops",
        "ovs_tx_mtu_exceeded_drops",
        "ovs_tx_qos_drops",
        "rx_crc_err",
        "rx_dropped",
        "rx_errors",
        "rx_frame_err",
        "rx_missed_errors",
        "rx_over_err",
        "tx_dropped",
        "tx_errors",
    }

    def ovs_stats_labels(self, port: D):
        for name, value in port.get("stats", {}).items():
            if value and port.get("admin_state") == "up" and name in self.OVS_ERRORS:
                yield f'<font color="red">{name} {human_readable(value)}</font>'

    def ovs_stats_tooltip(self, port: D):
        tip = []
        for name, value in port.get("stats", {}).items():
            tip.append(f"{name} {human_readable(value)}")
        return tip

    def ovs_port(self, port: D):
        if port.name in self.report.interfaces:
            self.edge(
                self.iface_node_id(port.name, ""),
                self.ovs_br_node_id(port.bridge),
                color="forestgreen",
            )
            return

        labels = self.ovs_base_labels(port)
        if port.type in ("dpdk", "dpdkvhostuserclient"):
            labels.extend(self.ovs_dpdk_labels(port))
            if "dpdk_devargs" in port.options:
                self.edge(
                    self.ovs_port_node_id(port.name),
                    pci_node_id(port.options.dpdk_devargs),
                    style="dashed",
                    color="darkorange",
                )

        iface = self.report.interfaces.get(port.name, None)
        if iface is not None:
            for ip in self.report.interfaces[port.name].get("ip", []):
                labels.append(f'<font color="purple">{ip}</font>')
            if "link" in iface:
                link_ns = ""
                if "link_netns" in iface:
                    link_ns = iface.link_netns
                    if link_ns == "0":
                        link_ns = ""
                link = self.find_iface(iface.link, link_ns)
                self.edge(
                    self.ovs_port_node_id(port.name),
                    self.iface_node_id(link.name, link_ns),
                    style="dashed",
                    color="forestgreen",
                )
            if "master" in iface:
                self.edge(
                    self.iface_node_id(iface.master, ""),
                    self.ovs_port_node_id(port.name),
                    style="solid",
                    color="forestgreen",
                )
        labels.extend(self.ovs_stats_labels(port))

        self.node(
            self.ovs_port_node_id(port.name),
            labels,
            tooltip=self.ovs_stats_tooltip(port),
            color="forestgreen",
        )
        self.edge(
            self.ovs_br_node_id(port.bridge),
            self.ovs_port_node_id(port.name),
            color="forestgreen",
        )

        if port.type == "bond":
            for member in port.members.values():
                if member.name in self.report.interfaces:
                    self.edge(
                        self.ovs_port_node_id(port.name),
                        self.iface_node_id(member.name, ""),
                        style="solid",
                        color="forestgreen",
                    )
                    continue

                labels = self.ovs_base_labels(member)
                if member.type == "dpdk":
                    labels.extend(self.ovs_dpdk_labels(member))
                    self.edge(
                        self.ovs_port_node_id(member.name),
                        pci_node_id(member.options.dpdk_devargs),
                        style="dashed",
                        color="darkorange",
                    )
                labels.extend(self.ovs_stats_labels(member))
                self.node(
                    self.ovs_port_node_id(member.name),
                    labels,
                    tooltip=self.ovs_stats_tooltip(member),
                    color="forestgreen",
                )
                self.edge(
                    self.ovs_port_node_id(port.name),
                    self.ovs_port_node_id(member.name),
                    style="solid",
                    color="forestgreen",
                )

    def irq_counters(self, cpu: int) -> tuple[int, int]:
        counter = 0
        bound = 0
        for irq in self.report.irqs.values():
            if not irq.irq.isdigit():
                continue
            if cpu in irq.get("effective_affinity", []):
                bound += 1
            counter += irq.counters[cpu]
        return counter, bound

    def irq_counters_tooltip(self, cpus: set[int]) -> str:
        tooltip = []
        for c in cpus:
            counter, bound = self.irq_counters(c)
            if counter < 42:  # XXX: how about 1337 maybe?
                continue
            counter = human_readable(counter)
            tooltip.append(f"CPU {c} bound_irqs={bound} interrupts={counter}")
        return format_label(tooltip)

    def phy_numa(self, numa: D):
        model = "<b>Unknown Processor Model</b>"
        for i, proc in enumerate(self.report.hardware.processor):
            if i == numa.id:
                model = f"<b>{proc.model}</b>"
        with self.cluster(model, style="dotted", color="blue"):
            housekeeping_cpus = set(numa.cpus)

            ovs_pmds = {}
            for pmd in self.report.ovs.pmds.values():
                if pmd.numa != numa.id:
                    continue
                p = ovs_pmds.setdefault(
                    pmd.core,
                    D(cpu=pmd.core, isolated=pmd.isolated, rxqs=0, usage=0),
                )
                for rxq in pmd.rxqs:
                    if rxq.enabled:
                        p.rxqs += 1
                        p.usage += rxq.usage

            if ovs_pmds:
                labels = ["<b>OVS DPDK</b>"]
                for pmd in ovs_pmds.values():
                    irqs, _ = self.irq_counters(pmd.cpu)
                    labels.append(
                        f"CPU {pmd.cpu} rxqs={pmd.rxqs} usage={pmd.usage}% irqs={human_readable(irqs)}"
                    )

                self.node(
                    f"phy_cpus_ovs_{numa.id}",
                    labels,
                    tooltip=self.irq_counters_tooltip(ovs_pmds.keys()),
                    color="blue",
                )

            housekeeping_cpus -= ovs_pmds.keys()

            for vm in self.report.get("vms", {}).values():
                for vnuma in vm.numa.values():
                    if numa.id not in vnuma.host_numa:
                        continue
                    host_cpus = set()
                    for vcpu in vnuma.vcpus:
                        host_cpus.update(vm.vcpu_pinning[vcpu])
                    self.node(
                        f"phy_cpus_{vm.name}_{numa.id}",
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
            if numa.offline_cpus:
                self.node(
                    f"phy_cpus_offline_{numa.id}",
                    [
                        '<font color="gray"><b>Offline</b></font>',
                        f'<font color="gray">CPUs {bit_list(numa.offline_cpus)}</font>',
                    ],
                    tooltip=self.irq_counters_tooltip(numa.offline_cpus),
                    color="gray",
                )

        labels = [f"<b>memory {human_readable(numa.total_memory, 1024)}</b>"]
        for size, num in numa.get("hugepages", {}).items():
            if not num:
                continue
            labels.append(f"{human_readable(size, 1024)} hugepages: {num}")

        self.node(f"memory_{numa.id}", labels, color="red")
        self.phy_pci_nics(numa)

    def phy_pci_nics(self, numa: D):
        pci_bridges = {}
        for nic in numa.get("pci_nics", {}).values():
            pci_bridges.setdefault(nic.pci_bridge, []).append(nic)

        for bridge, nics in pci_bridges.items():
            if len(nics) == 1:
                labels = [f"<b>{nics[0].pci_id}</b>"]
                if "kernel_driver" in nics[0]:
                    labels.append(nics[0].kernel_driver)
                self.node(
                    pci_node_id(nics[0].pci_id),
                    labels,
                    tooltip=nics[0].device,
                    color="darkorange",
                )
            else:
                with self.cluster(
                    f"PCI bridge {bridge}", style="dashed", color="darkorange"
                ):
                    for nic in nics:
                        labels = [f"<b>{nic.pci_id}</b>"]
                        if "kernel_driver" in nic:
                            labels.append(nic.kernel_driver)
                        self.node(
                            pci_node_id(nic.pci_id),
                            labels,
                            tooltip=nic.device,
                            color="darkorange",
                        )


def pci_node_id(pci_id):
    return f"pci_{pci_id}"


def wrap_text(text: str, margin: int) -> list[str]:
    lines = []
    more = True

    while more:
        if len(text) <= margin:
            # whole text fits in a single line
            line = text
            more = False
        else:
            # find split point, preferably before margin
            split = -1
            width = 0
            markup = 0
            for w, t in enumerate(text):
                if width >= margin and split != -1:
                    break
                if t in " \t,>":
                    split = w
                if t == "<":
                    markup += 1
                elif t == ">":
                    markup -= 1
                if markup == 0:
                    width += 1
            if split == -1:
                # no space found to split, print a long line
                line = text
                more = False
            else:
                line = text[: split + 1]
                text = text[split + 1 :]
                # find start of next word
                while text and text[0] in " \t":
                    text = text[1:]
                if not text:
                    # only trailing whitespace, we're done
                    more = False
        lines.append(line)

    return lines


def format_label(lines: list[str], max_width: int = 0) -> str:
    if isinstance(lines, str):
        lines = [lines]
    if max_width:
        out = []
        for line in lines:
            out += wrap_text(line, max_width)
        lines = out
    if any(line.startswith("<") for line in lines):
        return "<" + "<br/>".join(lines) + ">"
    return "\\n".join(lines)
