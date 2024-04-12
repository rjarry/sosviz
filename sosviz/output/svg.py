# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

import subprocess

from .dot import SOSGraph


def render(report, **opts):
    src = SOSGraph(report).source()
    subprocess.run(["dot", "-T", "svg"], input=src, text=True, check=True)
