from .vagrant import QEMUSnapshot, parse_qemu_img_snapshot_list


def test_parse_qemu_snapshot1():
    output = """
    Snapshot list:
    ID        TAG               VM SIZE                DATE     VM CLOCK     ICOUNT
    1         build                 0 B 2024-06-23 01:57:19 00:00:00.000          0
    2         2267602          3.05 GiB 2024-06-23 16:31:11 00:05:17.849
    3         3125217          2.35 GiB 2024-06-23 16:35:46 00:02:59.605
    4         4056254          2.05 GiB 2024-06-23 16:39:09 00:01:39.459
    5         890830           2.92 GiB 2024-06-23 16:43:45 00:03:26.232
    6         3161102          1.93 GiB 2024-06-23 16:47:33 00:02:12.826
    7         4033631          1.96 GiB 2024-06-23 16:52:11 00:03:40.142
    8         4480730           1.9 GiB 2024-06-23 16:54:46 00:01:34.657
    9         4023057          1.93 GiB 2024-06-23 16:57:34 00:01:49.845
    10        4019474          3.56 GiB 2024-06-23 17:31:24 00:32:51.087
""".strip()
    assert len(list(parse_qemu_img_snapshot_list(output))) == 10


def test_parse_qemu_snapshot2():
    output = """
Snapshot list:
ID        TAG               VM SIZE                DATE     VM CLOCK     ICOUNT
1         build                 0 B 2024-06-23 22:33:39 00:00:00.000          0
""".strip()
    assert list(parse_qemu_img_snapshot_list(output)) == [QEMUSnapshot(ID=1, Tag="build")]
