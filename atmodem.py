#!/usr/bin/env python3
import re
import logging
import serial

class atmodem:
    def __init__(self, name, at_dev):
        #self.at = ser(f"{name}_AT", at_dev)
        self._timeout = 60
        self._timeout_parse = 0.1
        self._serial = serial.Serial(at_dev, 115200,
                                     dsrdtr = True, rtscts = True,
                                     timeout = self._timeout)
        self._encoding = "GSM"
        self._requests = []
        self._response = []
        self._events = []
        self._logger = logging.getLogger(name)

    def encode(self, input: str, encoding: str) -> str:
        if encoding == 'GSM':
            ret = input
            #ret = str.encode('ascii').decode('ascii')
        elif encoding == 'UCS2':
            data = input.encode('utf-16be')
            ret = data.hex().upper()
        else:
            raise Exception(f"Unknown encoding {encoding}: {input}")
        return ret

    def decode(self, input: str, encoding: str) -> str:
        if encoding == 'GSM':
            ret = input
            #ret = str.encode('ascii').decode('ascii')
        elif encoding == 'UCS2':
            ret = bytearray.fromhex(input).decode('utf-16be')
        else:
            raise Exception(f"Unknown encoding {encoding}: {input}")
        return ret

    def _encode(self, input: str) -> str:
        return self.encode(input, self._encoding)

    def _decode(self, input: str) -> str:
        return self.decode(input, self._encoding)

    def cmd_test(self, cmd: str, enc_str=True):
        self._requests.append(("cmd", cmd, f"{cmd}=?", enc_str))

    def cmd_exec(self, cmd: str, enc_str=True):
        self._requests.append(("cmd", cmd, f"{cmd}", enc_str))

    def cmd_read(self, cmd: str, timeout=None, enc_str=True):
        self._requests.append(("cmd", cmd, f"{cmd}?", enc_str))
        return self.cmd_resp(cmd, timeout)

    def cmd_write(self, cmd: str, *args, enc_str=True):
        sargs = []
        for a in args:
            if type(a) == str:
                if enc_str:
                    sargs.append(f'"{self._encode(a)}"')
                else:
                    sargs.append(f'"{a}"')
            elif type(a) == int:
                sargs.append(str(a))
            else:
                raise Exception(f"Unknown cmd args type: {type(a)}: {a}")
        data = f"{cmd}=" + ",".join(sargs)
        self._requests.append(("cmd", cmd, data, enc_str))

    def cmd_write_data(self, data: str):
        self._requests.append(("data", data))

    def cmd_resp(self, cmd: str = None, timeout=None):
        self._requests.append(("resp", cmd, timeout))
        return self._proc()

    def wait_event(self, timeout = None):
        if self._events:
            return self._events.pop(0)
        self._requests.append(("wait", timeout))
        self._proc()
        if self._events:
            return self._events.pop(0)

    def _write(self, data: bytearray):
        self._logger.debug(f"COM ← {data}")
        self._serial.write(data)

    def _read(self, timeout = None):
        if timeout != None:
            self._serial.timeout = timeout
        resp = self._serial.readline()
        if resp:
            self._logger.debug(f"COM → {resp}")
        if timeout != None:
            self._serial.timeout = self._timeout
        return resp

    def _parse_resp(self, text: str, dec_str=True):
        #self._logger.debug(f"parse {text}")
        if re.fullmatch(r'\([^()]*\)', text):
            text = text[1:-1]
        resp = []
        # re.split(r'(\([^\)]*\)|\"[^\"]*\"|[0-9]+|[A-Z ]+)', text):
        for m in text.split(","):
            if m == '' or m == ',':
                continue
            elif m.startswith('"'):
                if dec_str:
                    resp.append(self._decode(m[1:-1]))
                else:
                    resp.append(m[1:-1])
            elif re.fullmatch(r'-?[0-9]+', m):
                resp.append(int(m))
            elif re.fullmatch(r'0x[0-9A-F]+', m):
                resp.append(int(m, 16))
            else:
                resp.append(m)
        return tuple(resp)

    def _parse_events(self, resp: str):
        if re.match(r'\+[A-Z]+:', resp):
            m = re.fullmatch(fr"(?P<cmd>.*):\s+(?P<resp>.*)", resp)
            self._events.append((m["cmd"], *self._parse_resp(m["resp"])))
            return True
        return False

    def _proc(self):
        while self._requests:
            req = self._requests.pop(0)
            #self._logger.debug(f"proc {req}")
            self._response = []

            op = req[0]
            if op == "raw":
                _, data = req
                self._write(req[1])

            elif op == "flush":
                _, timeout = req
                while True:
                    resp = self._read(timeout)
                    if not resp:
                        break

            elif op == "wait":
                _, timeout = req
                resp = self._read(timeout).decode("ascii").strip()
                if not resp:
                    return None
                if not self._parse_events(resp):
                    raise Exception(f"Unknown event: {resp}")
                return self._events[0]

            elif op == "cmd":
                _, cmd, data, enc_str = req
                if cmd.startswith("+"):
                    data = f"AT{data}\r"
                else:
                    data = f"{data}\r"
                self._write(data.encode("ascii"))
                cmd_data = self._requests and self._requests[0][0] == "data"
                while True:
                    resp = self._read(self._timeout_parse if cmd_data else None)
                    if not resp:
                        raise Exception(f"No response to {req}")
                    resp = resp.decode("ascii").strip()
                    if not resp:
                        continue
                    elif resp == "OK":
                        self._response = ("OK", self._response)
                        if self._requests and self._requests[0][0] == "resp":
                            resp = self._requests.pop(0)
                            _, cmd, timeout = resp
                            #self._logger.debug(f"resp {resp}: {self._response}")
                            return self._response
                        break
                    elif resp == "ERROR":
                        self._response = ("ERROR", self._response)
                        if self._requests and self._requests[0][0] == "resp":
                            resp = self._requests.pop(0)
                            _, cmd, timeout = resp
                            #self._logger.debug(f"resp {resp}: {self._response}")
                            return self._response
                        break
                    elif resp.startswith(f"{cmd}:"):
                        rcmd = cmd.replace("+", "\\+")
                        m = re.fullmatch(fr"{rcmd}:\s+(?P<resp>.*)", resp)
                        self._response.append(self._parse_resp(m["resp"], dec_str=enc_str))
                        #self._logger.debug(f"cmd resp {req}: {resp}, {self._response}")
                    elif resp.startswith("+CME ERROR"):
                        m = re.fullmatch(r"\+CME ERROR:\s+(?P<resp>.*)", resp)
                        self._response = ("+CME ERROR", [self._parse_resp(m["resp"], dec_str=enc_str)])
                        if self._requests and self._requests[0][0] == "resp":
                            resp = self._requests.pop(0)
                            _, cmd, timeout = resp
                            self._logger.debug(f"resp {resp}: {self._response}")
                            return self._response
                        break
                    elif resp == ">":
                        # Text input
                        req = self._requests.pop(0)
                        _, data = req
                        if self._encoding == "GSM":
                            lines = data.split('\n')
                            for i,line in enumerate(lines):
                                crlf = "\r" if i != len(lines) - 1 else ""
                                self._write(f'{line}{crlf}'.encode("ascii"))
                                resp = self._read(self._timeout_parse).decode('ascii').strip()
                                if resp != '>':
                                    raise Exception("CMD text mode no response")
                            self._write(b'\x1a')
                        else:
                            self._write(self._encode(data).encode("ascii"))
                            self._write(b'\x1a')
                        cmd_data = False
                    elif self._parse_events(resp):
                        continue
                    else:
                        self._response.append(self._decode(resp))
                        #raise Exception(f"Unrecognised response to {req}: {resp}")

            else:
                raise Exception(f"Unknown operation: {req}")
        return self._response

    def ping(self) -> bool:
        self.cmd_exec("AT")
        try:
            self.cmd_resp()
            return True
        except:
            return False

    def set_encoding(self, enc: str):
        # Encoding for +CSCS parameter is apparently always GSM
        self._encoding = "GSM"
        self.cmd_write("+CSCS", enc)
        self._encoding = enc

    def init(self):
        # AT for auto baud rate
        self._requests.append(("raw", b'ATATATAT\r'))
        self._requests.append(("flush", 0.1))
        # ESC in case it is waiting for GSM
        self._requests.append(("raw", b'\x1b\x1b\r'))
        self._requests.append(("flush", 0.1))
        # Disable command echo
        self.cmd_exec("ATE0")
        self.cmd_resp()
        self.set_encoding('GSM')
        if not self.ping():
            raise Exception("No ping reply")
