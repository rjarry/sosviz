# sosviz

Extract information from [`sos`](https://github.com/sosreport/sos) reports and
export it in other formats.

## Installation

```
pip install --user sosviz
```

System dependency to [`dot`](https://command-not-found.com/dot) from the
[`graphviz`](https://graphviz.org/) package.

## Usage

```
usage: sosviz [-h] [-V] [-d] [-f {dot,text,json,svg}] PATH

Collect information from an sos report folder and export it in other formats
on standard output.

positional arguments:
  PATH                  Path to an uncompressed sos report folder.

options:
  -h, --help            show this help message and exit
  -V, --version         Show version and exit.
  -d, --debug           Show debug info.
  -f {dot,text,json,svg}, --format {dot,text,json,svg}
                        Output format (default: svg).
```

Examples:

```
sosviz ~/tmp/sosreport > example.svg
```

```
sosviz -f dot ~/tmp/sosreport | dot -Tpng > example.png
```

```
sosviz --debug -f json ~/tmp/sosreport | jq -C | less -R
```

## Example SVG output

![example.svg](https://raw.githubusercontent.com/rjarry/sosviz/main/example.svg)
