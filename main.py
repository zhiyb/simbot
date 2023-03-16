#!/usr/bin/env python3
import os, re, datetime
import logging
import pyudev
import serial

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

class udev:
    def __init__(self):
        self.context = pyudev.Context()

    def device(self, devfile):
        return pyudev.Devices.from_device_file(self.context, devfile)

    def devfiles(path = "/dev"):
        return [path + "/" + f for f in os.listdir(path)]

class ser:
    def __init__(self, name, dev, type = "at"):
        self.logger = logging.getLogger(name)
        self.dev = dev
        self.type = type
        self.timeout = 0.1
        self.logger.debug(f"Opening {dev}")
        self.serial = serial.Serial(dev, 115200,
                                    dsrdtr = True, rtscts = True,
                                    timeout = self.timeout)

    def writeraw(self, data: bytearray):
        self.logger.debug(f"← {data}")
        self.serial.write(data)

    def writeascii(self, string: str):
        self.writeraw(string.encode('ascii'))

    def writeline(self, data: str):
        self.writeascii(f"{data}\r\n")

    def readline(self, timeout = None, strip = True):
        if timeout:
            self.serial.timeout = timeout
        while True:
            data = self.serial.readline()
            if data:
                self.logger.debug(f"→ {data}")
            data = data.decode('ascii')
            if not data:
                break
            if strip:
                data = data.strip()
            if data:
                break
        if timeout:
            self.serial.timeout = self.timeout
        return data

    def readall(self, timeout = None):
        data = True
        all = []
        while data:
            data = self.readline(timeout=timeout)
            all.append(data)
        return all

class sim7080:
    """
    SIM7080 UART interfaces:
    0 - Diagnostics 9206
    1 - NMEA 9206
    2 - AT Port 9206
    3 - QFLOG 9206
    4 - DAM 9206
    5 - Modem 9206
    """
    def __init__(self, name, at_dev):
        self.at = ser(f"{name}_AT", at_dev)
        self.encoding = "UCS2"
        self.logger = logging.getLogger(name)
        self.init()

    def error(self, err):
        self.logger.error(err)
        raise Exception(err)

    def check_ok(self, err="Failed to execute"):
        if self.at.readline() != "OK":
            self.error(err)

    def ping(self) -> bool:
        #self.logger.debug(self.ping.__name__)
        self.at.writeline("AT")
        return self.at.readline() == "OK"

    def test_sim(self) -> bool:
        self.at.writeline("AT+CPIN?")
        resp = self.at.readline()
        ok = self.at.readline() == "OK"
        return resp == "+CPIN: READY" and ok

    def subscriber_number(self) -> str:
        self.at.writeline("AT+CNUM")
        resp = self.at.readline()
        match = re.match(r'\+CNUM: (?:.+),\"(?P<num>.+)\",(?P<type>.+)$', resp)
        num = match["num"]
        ok = self.at.readline() == "OK"
        if not (ok and num):
            self.error("Failed to get subscriber number")
        return num

    def str(self, string: str) -> bytearray:
        if self.encoding == 'GSM':
            ret = string
            #ret = str.encode('ascii').decode('ascii')
        elif self.encoding == 'UCS2':
            data = string.encode('utf-16be')
            ret = data.hex()
        else:
            self.error(f"Unknown encoding {self.encoding} (str)")
        return ret.upper()

    def set_encoding(self, enc: str):
        self.at.writeline(f'AT+CSCS="{enc}"')
        if self.at.readline() != "OK":
            self.error(f"Failed to switch encoding to {enc}")
        self.encoding = enc

    def send_sms(self, num, text: str, enc="UCS2") -> int:
        self.logger.info(f"Sending SMS({enc}) to {num}: {text}")
        self.set_encoding(enc)
        self.at.writeline("AT+CMGF=1")
        self.check_ok()
        dcs = {"GSM": 0, "UCS2": 8}
        self.at.writeline(f'AT+CSMP=17,167,0,{dcs[enc]}')
        self.check_ok()
        if enc == "GSM":
            self.at.writeascii(f'AT+CMGS="{self.str(f"+{num}")}"')
            for line in text.split('\n'):
                self.at.writeraw(b'\r')
                if self.at.readline() != '>':
                    self.error("SMS no response")
                self.at.writeascii(line)
            self.at.writeraw(b'\x1a')
        else:
            self.at.writeascii(f'AT+CMGS="{self.str(f"+{num}")}"\r')
            if self.at.readline() != '>':
                self.error("SMS no response")
            self.at.writeascii(self.str(text))
            self.at.writeraw(b'\x1a')
        resp = self.at.readline(timeout=60)
        match = re.match(r'\+CMGS: (?P<mr>[0-9]+)', resp)
        if not match:
            self.error("Failed to send SMS")
        mr = int(match['mr'])
        self.check_ok()
        self.set_encoding('GSM')
        return mr

    def init(self):
        # Send ESC in case it is waiting for GSM
        self.at.writeraw(b'\x1b\x1b')
        self.at.readall()
        # Disable command echo
        self.at.writeline("ATE0")
        self.at.readall()
        self.set_encoding('GSM')
        # Test ping
        if not self.ping():
            self.error("No ping reply")
        if not self.test_sim():
            self.error("SIM card not ready")
        num = self.subscriber_number()
        self.logger.info(f"#: {num}")

        self.at.writeline("AT+CSCS=?")
        self.at.readall()
        time = datetime.datetime.now().ctime()
        #self.send_sms(recipient_no, f"{time}\n来摸鱼！")
        self.send_sms(recipient_no, f"{time}\nHello GSM\ntest", enc="GSM")
        self.send_sms(recipient_no, f"{time}\n蛤 UCS2 🤔\ntest", enc="UCS2")
        #self.send_sms(recipient_no, f"{time}\nHello 078\ntest")


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
    #print(sim.test_sim())

if __name__ == "__main__":
    main()
