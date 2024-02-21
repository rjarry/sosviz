# sosstat

Tool to extract statistics and sizing information from sos reports and database
dumps.

## Installation

```
pip install --user sosstat
```

## Usage

```
usage: sosstat [-h] [-d] [-f {dot,text,json}] PATH

Collect information from an sosreport and export it in other formats.

positional arguments:
  PATH                  Path to an uncompressed sosreport folder.

options:
  -h, --help            show this help message and exit
  -d, --debug           Show debug info.
  -f {dot,text,json}, --format {dot,text,json}
                        Output format (default: text).
```

## Generate Visual Representation

```
sosstat -f dot ~/tmp/sosreport | dot -Tsvg > sosreport.svg
```

Example:

![docs/example.png](https://gitlab.cee.redhat.com/rjarry/sosstat/-/raw/main/docs/example.png)
