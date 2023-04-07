#!/usr/bin/env python3
import logging
from datetime import datetime, timedelta
from atmodem import *

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
        self.state = "reset"
        self.num = None
        self.polltime = timedelta(seconds=10)
        self.time = datetime.utcnow() - 10 * self.polltime
        self._at = atmodem(f"{name}_AT", at_dev)
        self._events = []
        self._logger = logging.getLogger(name)

    def _set_encoding(self, enc: str):
        self._at.set_encoding(enc)

    def test_sim(self) -> bool:
        resp = self._at.cmd_read("+CPIN")
        return resp[1][0][0] == "READY"

    def dial(self) -> bool:
        raise Exception("TODO")
        resp = self._at.cmd_exec("ATD")
        return self._at.cmd_resp()

    def subscriber_number(self) -> str:
        self._at.cmd_exec("+CNUM")
        resp = self._at.cmd_resp()
        if resp[0] != "OK":
            self._logger.warning(f"Failed to get subscriber number: {resp}")
            return None
        num = resp[1][0][1]
        self._logger.info(f"#: {num}")
        return num

    def send_sms(self, num, text: str, enc="UCS2") -> int:
        self._logger.info(f"Sending SMS({enc}) to {num}: {text}")
        self._set_encoding(enc)
        dcs = {"GSM": 0, "UCS2": 8}
        self._at.cmd_write("+CSMP", 17, 167, 0, dcs[enc])

        self._at.cmd_write("+CMGS", f"+{num}")
        self._at.cmd_write_data(text)
        # Max response time: 60s
        resp = self._at.cmd_resp("+CMGS", timeout=65)
        if resp[0] != "OK":
            raise Exception("Failed to send SMS")
        self._set_encoding('GSM')

    def recv_sms(self, enc="UCS2"):
        self._set_encoding(enc)

        self._at.cmd_write("+CMGL", "ALL", enc_str=False)
        resp = self._at.cmd_resp()
        if resp[0] != "OK":
            raise Exception("Unable to read SMS")
        count = len(resp[1])
        for i in range(0, count, 2):
            info = resp[1][i]
            text = resp[1][i + 1]
            src = self._at.decode(info[2], "UCS2")
            self._logger.info(f"Received SMS from {src}: {text}")
            self._events.append({"type": "sms", "src": src, "info": info, "text": text})

        self._set_encoding('GSM')

    def poll(self, timeout=None):
        # Test ping
        if not self.test_sim():
            self._logger.warn(f"SIM card not ready")
            self.state = "reset"
            self.num = None
            return

        if self.state == "reset":
            self.num = self.subscriber_number()
            self._at.cmd_write("+CMGF", 1)
            self.state = "idle"

        if self.state == "idle":
            self.recv_sms()
            self.state = "ready"

        if self.state == "ready":
            resp = self._at.wait_event(timeout=timeout)
            if not resp:
                return None
            if resp[0] == "+CMTI":
                # Received new SMS
                self.recv_sms()
            else:
                self._logger.debug(resp)

    def proc(self, timeout=None):
        #self._at.cmd_read("+CNMI")

        if self._events:
            return self._events.pop(0)

        time = datetime.utcnow()
        if time - self.time >= self.polltime:
            self._logger.info(f"Polling")
            self.poll()
            if time - self.time >= 2 * self.polltime:
                self.time = time
            else:
                self.time += self.polltime

        if self._events:
            return self._events.pop(0)
        return None

    def init(self):
        self._logger.info(f"Init")
        self._at.init()
        #self.recv_sms()

    def test(self):
        self._logger.info(f"Test")

        # Verbose CME error
        self._at.cmd_write("+CMEE", 2)

        self._at.cmd_test("+CSCS")
        print(self._at.cmd_resp())

        # Get local timestamps
        self._at.cmd_write("+CLTS", 1)
        self._at.cmd_read("+CCLK")

        print(self._at.cmd_read("+CPSI"))

        self._at.cmd_exec("+CGNAPN")
        print(self._at.cmd_resp())

        self._at.cmd_exec("+CCID")
        self._logger.info(f"ICCID: {self._at.cmd_resp()[1][0]}")

        self._at.cmd_exec("+CIMI")
        self._logger.info(f"IMSI: {self._at.cmd_resp()[1][0]}")

        self._at.cmd_exec("+GSV")
        print(self._at.cmd_resp())

        print(self._at.cmd_read("+CURCCFG"))

        #timestr = datetime.datetime.now().ctime()
        #self.send_sms(**censored**, f"{timestr}\n蛤 UCS2 🤔\ntest")
