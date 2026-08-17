# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import re

from ..bits import bit_list, human_readable
from ..collect import D


def render(report: D, **opts):
    TextReport(report).render()


class TextReport:
    def __init__(self, report: D):
        self.report = report

    def render(self):
        r = self.report
        print(f"# {r.hostname} / {r.hardware.system}")
        print()
        print(f"linux {r.software.kernel}")
        for sw in "os_release", "rhosp_release":
            if sw in r.software:
                print(r.software[sw])
        if "ovs" in r:
            ovs = f"OVS {r.ovs.config.ovs_version}"
            if r.ovs.config.get("dpdk_initialized"):
                ovs += f" {r.ovs.config.dpdk_version}"
            print(ovs)

        self.numa_nodes()
        self.vms()
        self.networking()

    def vms(self):
        r = self.report
        if not r.get("vms"):
            return
        print()
        print("## VMs")
        for vm in r.vms.values():
            print()
            print(f"### {vm.name}")
            for numa in vm.get("numa", {}).values():
                vcpus = bit_list(numa.vcpus)
                host_cpus = set()
                for vcpu in numa.vcpus:
                    host_cpus.update(vm.vcpu_pinning.get(vcpu, set()))
                line = f"- numa {numa.id}: vCPUs {vcpus}"
                if host_cpus:
                    line += f", host CPUs {bit_list(host_cpus)}"
                cpu_numas = set()
                for n in r.numa.values():
                    if host_cpus & n.cpus:
                        cpu_numas.add(n.id)
                if cpu_numas:
                    line += f", host NUMA {bit_list(cpu_numas)}"
                line += f", memory {human_readable(numa.memory, 1024)}"
                print(line)

            for iface in vm.get("interfaces", []):
                self.vm_iface(iface)

    def vm_iface(self, iface: D):
        parts = [iface.type]
        if "socket" in iface:
            parts.append(iface.socket.rsplit("/", 1)[-1])
        elif "host_dev" in iface:
            parts.append(iface.host_dev)
        elif "net_dev" in iface:
            parts.append(iface.net_dev)
        if "vlan" in iface:
            parts.append(f"VLAN {iface.vlan}")
        if "bridge" in iface:
            parts.append(f"bridge {iface.bridge}")
        if "queues" in iface:
            parts.append(f"queues {iface.queues}")
        print(f"- {', '.join(parts)}")

    def networking(self):
        r = self.report
        has_ovs = bool(r.get("ovs", D()).get("bridges"))
        has_ifaces = bool(r.get("interfaces"))
        has_netns = bool(r.get("netns")) and any(r.netns.values())
        if not has_ovs and not has_ifaces and not has_netns:
            return

        print()
        print("## Networking")

        if has_ovs:
            for br in r.ovs.bridges.values():
                self.ovs_bridge(br)
            for port in r.ovs.ports.values():
                if port.type in ("vxlan", "geneve", "internal", ""):
                    continue
                if port.type == "patch":
                    continue
                if port.name not in r.interfaces:
                    self.ovs_port(port)

        if has_ifaces:
            for iface in r.interfaces.values():
                self.phy_iface(iface, netns="")

        if has_netns:
            for netns, ifaces in r.netns.items():
                if not ifaces:
                    continue
                print()
                print(f"### netns {netns}")
                for iface in ifaces.values():
                    self.phy_iface(iface, netns=netns)

    def ovs_bridge(self, br: D):
        r = self.report
        parts = [
            f"**{br.name}**",
            br.datapath,
            f"rules {br.of_rules}",
            f"ports {br.ports}",
        ]
        iface = r.interfaces.get(br.name)
        if iface:
            for ip in iface.get("ip", []):
                parts.append(ip)
        print(f"- {', '.join(parts)}")

        vxlan_ports = 0
        geneve_ports = 0
        for port in r.ovs.ports.values():
            if port.bridge != br.name:
                continue
            if port.type == "vxlan":
                vxlan_ports += 1
            if port.type == "geneve":
                geneve_ports += 1
        if vxlan_ports:
            print(f"  - {vxlan_ports} VXLAN ports")
        if geneve_ports:
            print(f"  - {geneve_ports} GENEVE ports")

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

    def ovs_port_has_issues(self, port: D) -> bool:
        if port.get("admin_state") == "up":
            for name, value in port.get("stats", {}).items():
                if value and name in self.OVS_ERRORS:
                    return True
        if port.get("link_state") not in ("up", None, "?"):
            return True
        return False

    def ovs_port_rxq_high_usage(self, port: D) -> bool:
        for pmd in self.report.ovs.pmds.values():
            for rxq in pmd.rxqs:
                if rxq.port == port.name and rxq.enabled and rxq.usage >= 80:
                    return True
        return False

    def ovs_port(self, port: D):
        has_issues = self.ovs_port_has_issues(port)
        high_usage = self.ovs_port_rxq_high_usage(port)
        if port.type == "bond":
            for member in port.members.values():
                has_issues = has_issues or self.ovs_port_has_issues(member)
                high_usage = high_usage or self.ovs_port_rxq_high_usage(member)
        if not has_issues and not high_usage:
            return

        r = self.report
        parts = [f"**{port.name}**", f"OVS {port.type}"]
        if "admin_state" in port and "link_state" in port:
            parts.append(f"state {port.admin_state}/{port.link_state}")
        if "tag" in port:
            parts.append(f"VLAN {port.tag}")

        if port.type in ("dpdk", "dpdkvhostuserclient"):
            if "dpdk_devargs" in port.options:
                numa_id = "N/A"
                for numa in r.numa.values():
                    if port.options.dpdk_devargs in numa.pci_nics:
                        numa_id = numa.id
                        break
                parts.append(f"{port.options.dpdk_devargs} NUMA {numa_id}")

        print(f"  - {', '.join(parts)}")
        self.ovs_port_errors(port, indent=4)
        self.ovs_port_rxqs(port, indent=4)

        if port.type == "bond":
            for member in port.members.values():
                mparts = [f"**{member.name}**", f"OVS {member.type}"]
                if "admin_state" in member and "link_state" in member:
                    mparts.append(f"state {member.admin_state}/{member.link_state}")
                if member.type == "dpdk" and "dpdk_devargs" in member.options:
                    mparts.append(member.options.dpdk_devargs)
                print(f"    - {', '.join(mparts)}")
                self.ovs_port_errors(member, indent=6)
                self.ovs_port_rxqs(member, indent=6)

    def ovs_port_errors(self, port: D, indent: int):
        if port.get("admin_state") != "up":
            return
        errors = []
        for name, value in port.get("stats", {}).items():
            if value and name in self.OVS_ERRORS:
                errors.append(f"{name} {human_readable(value)}")
        if errors:
            pad = " " * indent
            print(f"{pad}- errors: {', '.join(errors)}")

    def ovs_port_rxqs(self, port: D, indent: int):
        disabled = set()
        rxqs = []
        for pmd in self.report.ovs.pmds.values():
            for rxq in pmd.rxqs:
                if rxq.port == port.name:
                    if rxq.enabled and rxq.usage >= 80:
                        rxqs.append((rxq.rxq, pmd.core, pmd.numa, rxq.usage))
                    elif not rxq.enabled:
                        disabled.add(rxq.rxq)
        if not rxqs and not disabled:
            return
        pad = " " * indent
        for rxq, core, numa, usage in sorted(rxqs):
            print(f"{pad}- rxq {rxq} cpu {core} NUMA {numa} usage {usage}%")
        if disabled:
            print(f"{pad}- rxqs {bit_list(disabled)} disabled")

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
        r = self.report
        if netns == "" and iface.name in r.ovs.bridges:
            return
        if iface.name == "ovs-system":
            return
        if re.match(r"(genev|vxlan)_sys_\d+", iface.name):
            return

        is_down = "DOWN" in iface["flags"]
        has_no_carrier = "NO-CARRIER" in iface["flags"]
        has_errors = False
        errors = []
        if "LOWER_UP" in iface["flags"]:
            for name, value in iface.get("stats", {}).items():
                if value and name in self.NETDEV_ERRORS:
                    errors.append(f"{name} {human_readable(value)}")
            has_errors = bool(errors)

        if not is_down and not has_no_carrier and not has_errors:
            return

        parts = [f"**{iface.name}**"]

        kind = iface.get("kind")
        if kind == "bond" and "bond_mode" in iface:
            kind += f" {iface.bond_mode}"
        if kind == "vlan" and "vlan" in iface:
            kind += f" {iface.vlan}"
        if kind == "tun" and "tun_type" in iface:
            kind += f" {iface.tun_type}"
        if kind:
            parts.append(kind)
        if "device" in iface:
            parts.append(iface.device)

        for ip in iface.get("ip", []):
            parts.append(ip)

        if is_down:
            state = "DOWN"
        else:
            state = "UP"
        if has_no_carrier:
            state += ",NO-CARRIER"
        elif "LOWER_UP" in iface["flags"]:
            state += ",LOWER_UP"
        parts.append(f"state {state}")

        print(f"- {', '.join(parts)}")
        if errors:
            print(f"  - errors: {', '.join(errors)}")

    def irq_counters(self, cpu: int) -> tuple:
        counter = 0
        bound = 0
        for irq in self.report.irqs.values():
            if not irq.irq.isdigit():
                continue
            if cpu in irq.get("effective_affinity", []):
                bound += 1
            counter += irq.counters[cpu]
        return counter, bound

    def numa_nodes(self):
        r = self.report
        if not r.get("numa"):
            return
        print()
        print("## NUMA Topology")
        for numa in r.numa.values():
            print()
            self.phy_numa(numa)

    def phy_numa(self, numa: D):
        r = self.report
        for i, proc in enumerate(r.hardware.processor):
            if i == numa.id:
                print(f"### NUMA {numa.id} - {proc.model}")
                break
        else:
            print(f"### NUMA {numa.id}")

        mem_parts = [f"memory {human_readable(numa.total_memory, 1024)}"]
        for size, num in numa.get("hugepages", {}).items():
            if num:
                mem_parts.append(f"{human_readable(size, 1024)} hugepages: {num}")
        print(f"- {', '.join(mem_parts)}")

        ovs_pmds = {}
        for pmd in r.ovs.pmds.values():
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
            print(f"- OVS DPDK: CPUs {bit_list(ovs_pmds.keys())}")
            for pmd in ovs_pmds.values():
                irqs, bound = self.irq_counters(pmd.cpu)
                line = (
                    f"  - CPU {pmd.cpu} rxqs={pmd.rxqs}"
                    f" usage={pmd.usage}%"
                    f" irqs={human_readable(irqs)}"
                )
                if bound:
                    line += f" bound={bound}"
                print(line)

        housekeeping_cpus = set(numa.housekeeping_cpus) - ovs_pmds.keys()
        isolated_cpus = set(numa.isolated_cpus) - ovs_pmds.keys()

        for vm in r.get("vms", {}).values():
            for vnuma in vm.numa.values():
                if numa.id not in vnuma.host_numa:
                    continue
                host_cpus = set()
                for vcpu in vnuma.vcpus:
                    host_cpus.update(vm.vcpu_pinning[vcpu])
                noisy = []
                for cpu in sorted(host_cpus):
                    irqs, bound = self.irq_counters(cpu)
                    if irqs > 0:
                        noisy.append(
                            f"CPU {cpu} irqs={human_readable(irqs)} bound={bound}"
                        )
                if noisy:
                    print(f"- VM {vm.name} IRQ noise: {', '.join(noisy)}")
                housekeeping_cpus -= host_cpus
                isolated_cpus -= host_cpus

        if isolated_cpus:
            noisy = []
            for cpu in sorted(isolated_cpus):
                irqs, bound = self.irq_counters(cpu)
                if irqs > 0:
                    noisy.append(f"CPU {cpu} irqs={human_readable(irqs)} bound={bound}")
            if noisy:
                print(f"- isolated IRQ noise: {', '.join(noisy)}")

        print(f"- housekeeping: CPUs {bit_list(housekeeping_cpus)}")

        if numa.offline_cpus:
            print(f"- offline: CPUs {bit_list(numa.offline_cpus)}")

        for nic in numa.get("pci_nics", {}).values():
            parts = [nic.pci_id]
            if "kernel_driver" in nic:
                parts.append(nic.kernel_driver)
            if "netdev" in nic:
                parts.append(nic.netdev)
            print(f"- NIC {', '.join(parts)}")
