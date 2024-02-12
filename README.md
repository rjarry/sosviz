# sosstat

Tool to extract statistics and sizing information from sos reports and database
dumps.

## NFV Diagnostics

Example run:

```console
$ python -m sosstat -f text ~/tmp/sosreport-ce3c3fd80dab8cf56ab
{'numa': {0: {'cpus': [(0, 48), (1, 49), (2, 50), (3, 51), (4, 52), (5, 53), (6, 54), (7, 55),
                       (8, 56), (9, 57), (10, 58), (11, 59), (12, 60), (13, 61), (14, 62), (15, 63),
                       (16, 64), (17, 65), (18, 66), (19, 67), (20, 68), (21, 69), (22, 70),
                       (23, 71)],
              'hugepages': {2097152: 0, 1073741824: 170},
              'pci_nics': {'13:00.0': {'device': 'Intel Corporation I350 Gigabit Network '
                                                 'Connection [8086:1521] (rev 01)',
                                       'kernel_driver': 'igb',
                                       'pci_id': '13:00.0'},
                           '13:00.1': {'device': 'Intel Corporation I350 Gigabit Network '
                                                 'Connection [8086:1521] (rev 01)',
                                       'kernel_driver': 'igb',
                                       'pci_id': '13:00.1'},
                           '13:00.2': {'device': 'Intel Corporation I350 Gigabit Network '
                                                 'Connection [8086:1521] (rev 01)',
                                       'kernel_driver': 'igb',
                                       'pci_id': '13:00.2'},
                           '13:00.3': {'device': 'Intel Corporation I350 Gigabit Network '
                                                 'Connection [8086:1521] (rev 01)',
                                       'kernel_driver': 'igb',
                                       'pci_id': '13:00.3'},
                           '5d:00.0': {'device': 'Mellanox Technologies MT27710 Family [ConnectX-4 '
                                                 'Lx] [15b3:1015]',
                                       'kernel_driver': 'mlx5_core',
                                       'pci_id': '5d:00.0'},
                           '5d:00.1': {'device': 'Mellanox Technologies MT27710 Family [ConnectX-4 '
                                                 'Lx] [15b3:1015]',
                                       'kernel_driver': 'mlx5_core',
                                       'pci_id': '5d:00.1'}},
              'total_memory': 202229755904},
          1: {'cpus': [(24, 72), (25, 73), (26, 74), (27, 75), (28, 76), (29, 77), (30, 78),
                       (31, 79), (32, 80), (33, 81), (34, 82), (35, 83), (36, 84), (37, 85),
                       (38, 86), (39, 87), (40, 88), (41, 89), (42, 90), (43, 91), (44, 92),
                       (45, 93), (46, 94), (47, 95)],
              'hugepages': {2097152: 0, 1073741824: 170},
              'pci_nics': {'af:00.0': {'device': 'Mellanox Technologies MT27710 Family [ConnectX-4 '
                                                 'Lx] [15b3:1015]',
                                       'kernel_driver': 'mlx5_core',
                                       'pci_id': 'af:00.0'},
                           'af:00.1': {'device': 'Mellanox Technologies MT27710 Family [ConnectX-4 '
                                                 'Lx] [15b3:1015]',
                                       'kernel_driver': 'mlx5_core',
                                       'pci_id': 'af:00.1'}},
              'total_memory': 202886791168}}}
```
