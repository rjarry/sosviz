# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2024 Robin Jarry

from ..bits import bit_list


def render(report, **opts):
    once = False
    for name, data in report.items():
        if once:
            print()
        else:
            once = True
        print("========================================")
        print(name)
        print("========================================")
        for key, val in data.items():
            print()
            print(key)
            print("----------------------------------------")
            print()
            print_value(val)



def print_value(val, indent=""):
    if isinstance(val, (set, list)):
        if all(isinstance(v, int) for v in val):
            print(indent + bit_list(val))
        elif all(isinstance(v, str) for v in val):
            print(indent + f"\n{indent}".join(val))
        else:
            for v in val:
                print_value(v, indent)

    elif isinstance(val, dict):
        for k, v in val.items():
            if isinstance(k, str):
                print(f"{indent}{k}: {v}")

    else:
        print(f"{indent}{val}")
