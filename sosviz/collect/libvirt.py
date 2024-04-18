# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import xml.etree.ElementTree as ET

from . import D
from ..bits import parse_cpu_set


def parse_report(path: pathlib.Path, data: D):
    data.vms = vms = D()
    for f in path.glob("etc/libvirt/qemu/*.xml"):
        xml = ET.parse(f).getroot()
        name = xml.find("./name").text
        vms[name] = vm = D(name=name)
        vm_cpu(vm, xml)
        vm_memory(vm, xml)
        vm_interfaces(vm, xml)


def vm_cpu(vm, xml):
    cpu = xml.find("./cpu")
    if cpu:
        vm.cpu_mode = cpu.get("mode")

    topo = xml.find("./cpu/topology")
    if topo:
        vm.topology = t = D()
        for attr in "sockets", "dies", "cores", "threads":
            t[attr] = int(topo.get(attr, "1"))

    for numa in xml.findall("./cpu/numa/cell"):
        numa_id = int(numa.get("id", "0"))
        vm.setdefault("numa", D())[numa_id] = D(
            id=numa_id,
            memory=int(numa.get("memory", "0")) * multiplier(numa.get("unit")),
            mem_access=numa.get("memAccess"),
            vcpus=parse_cpu_set(numa.get("cpus", str(numa_id))),
        )
    if "numa" not in vm:
        memory = xml.find("./memory")
        vcpu = xml.find("./vcpu")
        vm.numa = D()
        vm.numa[0] = D(
            id=0,
            memory=int(memory.text) * multiplier(memory.get("unit")),
            vcpus=set(range(int(vcpu.text))),
            host_numa=set(),
        )

    vm.vcpu_pinning = D()
    for vcpupin in xml.findall("./cputune/vcpupin"):
        vcpu = int(vcpupin.get("vcpu"))
        cpuset = parse_cpu_set(vcpupin.get("cpuset"))
        vm.vcpu_pinning[vcpu] = cpuset


def vm_memory(vm, xml):
    memory = xml.find("./memory")
    if memory:
        vm.memory = int(memory.text) * multiplier(memory.get("unit"))

    for node in xml.findall("./numatune/memnode"):
        numa_id = int(node.get("cellid", "0"))
        nodeset = parse_cpu_set(node.get("nodeset"))
        vm.setdefault("numa", D()).setdefault(numa_id, D()).host_numa = nodeset

    for page in xml.findall("./memoryBacking/hugepages/page"):
        node_set = parse_cpu_set(page.get("nodeset"))
        size = int(page.get("size")) * multiplier(page.get("unit"))
        for numa in vm.get("numa", D()).values():
            if node_set == numa.get("host_numa"):
                numa.hugepage_size = size


def vm_interfaces(vm, xml):
    for iface in xml.findall("./devices/interface"):
        iftype = iface.get("type")
        if iftype == "vhostuser":
            vm.setdefault("interfaces", []).append(
                D(
                    type=iftype,
                    queues=int(xpath(iface, "driver").get("queues", "1")),
                    socket=xpath(iface, "source").get("path"),
                )
            )
        elif iftype == "bridge":
            vm.setdefault("interfaces", []).append(
                D(
                    type="virtio-kernel",
                    bridge=xpath(iface, "source").get("bridge"),
                    net_dev=xpath(iface, "target").get("dev"),
                    ovs_port=xpath(iface, "virtualport/parameters").get("interfaceid"),
                )
            )
        elif iftype == "hostdev":
            src = iface.find("./source/address")
            domain = int(src.get("domain", "0x0"), 16)
            bus = int(src.get("bus", "0x0"), 16)
            slot = int(src.get("slot", "0x0"), 16)
            function = int(src.get("function", "0x0"), 16)
            dev = D(
                type="sriov",
                host_dev=f"{domain:04x}:{bus:02x}:{slot:02x}.{function:01x}",
            )
            for vlan in iface.findall("./vlan/tag"):
                dev.vlan = int(vlan.get("id"))
            vm.setdefault("interfaces", []).append(dev)

    for pci in xml.findall("./devices/hostdev[@type='pci']/source/address"):
        domain = int(pci.get("domain", "0x0"), 16)
        bus = int(pci.get("bus", "0x0"), 16)
        slot = int(pci.get("slot", "0x0"), 16)
        function = int(pci.get("function", "0x0"), 16)
        vm.setdefault("interfaces", []).append(
            D(
                type="sriov",
                host_dev=f"{domain:04x}:{bus:02x}:{slot:02x}.{function:01x}",
            )
        )


def xpath(node: ET.Element, path: str) -> ET.Element:
    n = node.find(path)
    if n is None:
        n = ET.Element(pathlib.Path(path).name)
    return n


def multiplier(unit):
    if isinstance(unit, str):
        if unit.startswith("Ki"):
            return 1024
        if unit.startswith("Mi"):
            return 1024 * 1024
        if unit.startswith("Gi"):
            return 1024 * 1024
    return 1
