import argparse
from device_studio.protocol import package
p=argparse.ArgumentParser();p.add_argument('binary');p.add_argument('output');p.add_argument('--name',choices=['Smartwatch','Duello'],required=True)
a=p.parse_args();print(package(a.binary,a.output,a.name))
