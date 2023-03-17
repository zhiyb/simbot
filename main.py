#!/usr/bin/env python3
import os, re, time, datetime
import logging
import pyudev
import serial
from atmodem import *
from sim7080 import *

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

class udev:
    def __init__(self):
        self.context = pyudev.Context()

    def device(self, devfile):
        return pyudev.Devices.from_device_file(self.context, devfile)

    def devfiles(path = "/dev"):
        return [path + "/" + f for f in os.listdir(path)]

def main():
    ud = udev()
    sims = []
    for devpath in udev.devfiles():
        if os.path.basename(devpath).startswith("ttyUSB"):
            dev = ud.device(devpath)
            #print(dict(dev.properties.items()))
            if dev.properties["ID_MODEL"].startswith("SimTech") and dev.properties["ID_USB_INTERFACE_NUM"] == "02":
                sims.append(sim7080("SIM7080", devpath))

    sim = sims[0]
    sim.init()
    sim.test()
    #print(sim.test_sim())

    while True:
        sim.proc()
        time.sleep(1)

if __name__ == "__main__":
    main()
