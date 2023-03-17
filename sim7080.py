#!/usr/bin/env python3
import re, time, datetime
import logging
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
        self._at.cmd_write("+CMGF", 1)
        dcs = {"GSM": 0, "UCS2": 8}
        self._at.cmd_write("+CSMP", 17, 167, 0, dcs[enc])

        self._at.cmd_write("+CMGS", f"+{num}")
        self._at.cmd_write_data(text)
        # Max response time: 60s
        resp = self._at.cmd_resp("+CMGS", timeout=65)
        if resp[0] != "OK":
            raise Exception("Failed to send SMS")
        self._set_encoding('GSM')

    def init(self):
        self._logger.info(f"Init")
        self._at.init()
        self.recv_sms()

    def test(self):
        self._logger.info(f"Test")
        # Test ping
        if not self.test_sim():
            raise Exception("SIM card not ready")
        self.subscriber_number()

        self._at.cmd_test("+CSCS")
        timestr = datetime.datetime.now().ctime()
        #self.send_sms(**censored**, f"{timestr}\n蛤 UCS2 🤔\ntest")

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
        pass

    def proc(self, timeout=None):
        #self._at.cmd_read("+CNMI")

        if self._events:
            return self._events.pop(0)

        resp = self._at.wait_event(timeout=timeout)
        if not resp:
            return None
        if resp[0] == "+CMTI":
            # Received new SMS
            self.recv_sms()
        else:
            self._logger.debug(resp)

        if self._events:
            return self._events.pop(0)
        return None
