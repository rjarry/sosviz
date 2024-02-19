# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import pathlib
import re

from . import D


RPMS_OF_INTEREST_RE = re.compile(
    r"^(\S*(?:openvswitch|ovn|dpdk|tuned|libvirt|qemu)\S*)\s", re.MULTILINE
)
PODMAN_PS_RE = re.compile(r"^[a-f0-9]+\s+(\S+)\s", re.MULTILINE)


def parse_report(path: pathlib.Path, data: D):
    data.software = sw = D()
    for f in "etc/rhosp-release", "etc/redhat-release":
        f = path / f
        if f.is_file():
            sw[f.name.replace("-", "_")] = f.read_text().strip()
    rpms = set()
    for match in RPMS_OF_INTEREST_RE.finditer((path / "installed-rpms").read_text()):
        rpms.add(match.group(1))
    sw.rpms = rpms

    containers = set()
    podman_ps = path / "sos_commands/podman/podman_ps"
    if podman_ps.is_file():
        for match in PODMAN_PS_RE.finditer(podman_ps.read_text()):
            _, _, name = match.group(1).partition("/")
            if "libvirt" in name or "qemu" in name or "ovn" in name:
                containers.add(name)
    sw.containers = containers

    match = re.search(r"/boot/vmlinuz-(\S+)", (path / "proc/cmdline").read_text())
    if match:
        sw.kernel = match.group(1)
