import argparse
from device_studio.protocol import package
p=argparse.ArgumentParser(description='DeviceBoot .dfw paketi olusturur; kimlik ve surum binary descriptorundan okunur.')
p.add_argument('binary');p.add_argument('output');p.add_argument('--name',required=True)
p.add_argument('--id',dest='app_id',type=lambda value:int(value,0),help='Istege bagli descriptor kimlik kontrolu; yeni uygulamalar icin 3 ve uzeri')
p.add_argument('--version',type=int,help='Istege bagli descriptor surum kontrolu')
a=p.parse_args();print(package(a.binary,a.output,a.name,version=a.version,app_id=a.app_id))
