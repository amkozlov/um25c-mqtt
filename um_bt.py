#!/usr/bin/python3

# sudo systemctl start bluetooth
# echo "power on" | bluetoothctl

import collections
import sys
import argparse
import datetime
import time
import struct
#import pickle
from bluetooth_socket import *

use_bluez = False

class UMDevice:

  def __init__(self, mac=None):
    self.type = "UM25C"
    if mac:
      self.host = mac
      self.port = 1  
      self.name = self.type
    else:
      self.discover()
    self.sn = self.host.replace(":", "")  
    self.connect()

  def discover(self):
    # Automagically find USB meter
    print(f"Looking for {self.type} devices nearby...")
    nearby_devices = discover_devices(lookup_names=True)

    addr = None
    for v in nearby_devices:
      if self.type in v[1]:
        print("Found", v[0])
        addr = v[0]
        break

    if addr is None:
      print("No address provided", file=sys.stderr)
      quit()

    service_matches = find_service(address=addr)

    if len(service_matches) == 0:
      print("No services found for address ", addr, file=sys.stderr)
      quit()

    first_match = service_matches[0]
    print(first_match)
    self.port = first_match["port"]
    self.name = first_match["name"]
    self.host = first_match["host"]

    if self.host is None or self.port is None:
       print("Host or port not specified", file=sys.stderr)
       quit()

  def connect(self):    
    print('Connecting to "{}" on {}:{}'.format(self.name, self.host, self.port))
    if use_bluez:
      self.sock = BluetoothSocket(RFCOMM)
      res = self.sock.connect((self.host, self.port))
    else:
      self.sock = BluetoothSocket(self.host)
      res = self.sock.connect()
    return res

  # Process socket data from USB meter and extract volts, amps etc.
  def parse_data(self, d):

    data = {}

    data["Volts"] = struct.unpack(">h", d[2 : 3 + 1])[0] / 1000.0  # volts
    data["Amps"] = struct.unpack(">h", d[4 : 5 + 1])[0] / 10000.0  # amps
    data["Watts"] = struct.unpack(">I", d[6 : 9 + 1])[0] / 1000.0  # watts
    data["temp_C"] = struct.unpack(">h", d[10 : 11 + 1])[0]  # temp in C
    data["temp_F"] = struct.unpack(">h", d[12 : 13 + 1])[0]  # temp in F

    utc_dt = datetime.datetime.now(datetime.timezone.utc)  # UTC time
    dt = utc_dt.astimezone()  # local time
    data["time"] = dt

    g = 0
    for i in range(16, 95, 8):
        ma, mw = struct.unpack(">II", d[i : i + 8])  # mAh,mWh respectively
        gs = str(g)
        data[gs + "_mAh"] = ma
        data[gs + "_mWh"] = mw
        g += 1

    data["data_line_pos_volt"] = struct.unpack(">h", d[96: 97 + 1])[0] / 100.0
    data["data_line_neg_volt"] = struct.unpack(">h", d[98: 99 + 1])[0] / 100.0
    data["resistance"] = struct.unpack(">I", d[122: 125 + 1])[0] / 10.0  # resistance
    return data

  def fetch_data(self):
    # Send request to USB meter
    d = b""

    while len(d) < 130: 
      self.sock.send((0xF0).to_bytes(1, byteorder="big"))
      d += self.sock.recv(130)

    data = self.parse_data(d)

    print("%s: %fV %fA %fW %fmWh" % (data["time"], data["Volts"], data["Amps"], data["Watts"], data["0_mWh"]))

    return data

  def close(self):
    self.sock.close()

