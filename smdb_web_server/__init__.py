import asyncio
from typing import Callable, Dict, Optional, Union, Any, List
from os import path
from smdb_logger import Logger, LEVEL
from json import dumps
from threading import Thread, Event
from time import perf_counter_ns
from enum import Enum

class KnownError(Exception):
    def __init__(self, reason: str, response_code: int) -> None:
        self.response = ResponseCode(response_code, reason)
    
    def __str__(self) -> str:
        return f"Reason: {self.response.name}, Code: {self.response.value}"
    
class CloseException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class ResponseCode():
    def __init__(self, value: int, name: str):
        self.value = value
        self.name = name

    def __str__(self) -> str:
        return f"{self.value} {self.name}"

class Timer():
    def __init__(self):
        self.start = perf_counter_ns()
        self.end = 0
    
    def stop(self):
        self.end = perf_counter_ns()

    def __str__(self) -> str:
        return f"{(self.end - self.start)/1000000}"

class Protocol(Enum):
    Get = "GET"
    Put = "PUT"

NotFound = ResponseCode(404, "Not Found")
Ok = ResponseCode(200, "Ok")
InternalServerError = ResponseCode(500, "Internal Server Error")
TPot = ResponseCode(418, "I'm a teapot")

get_rules: Dict[str, Callable[[Dict[str, str]], None]] = {}
put_rules: Dict[str, Callable[[bytes], None]] = {}
pageTitle: str = None
html_template: str = "<html><header><link rel='stylesheet' href='/static/style.css' /><title>{title}</title></header><body>{content}</body></html>"
http_header: str = "{version_info} {response_code}\r\nContent-Length: {length}\r\nContent-Type: {content_type};\r\nServer-Timing: {timing}\r\n\r\n"
cwd: str = "."

TEMPLATES: Dict[str, str] = {}
STATIC: Dict[str, str] = {}

class HTTPRequestHandler():
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, logger: Logger = None) -> None:
        self.reader = reader
        self.writer = writer
        self.headers: Dict[str, str] = None
        self.path: str = ""
        self.path_params: str = ""
        self.data: str = ""
        self.version: str = "HTTP/1.0"
        self.logger = logger
        self.close_event = Event()

    async def handle_request(self):
        try:
            tmp = await self.reader.readuntil("\r\n\r\n".encode())
            tmp = tmp.decode().split("\r\n")
            method, tmp_path, _ = tmp[0].split(" ")
            tmp_path = tmp_path.split("?")
            self.path_params = {item.split("=")[0]: item.split("=")[1] for item in tmp_path[-1].split("&") if len(item.split("=")) == 2}
            self.path = tmp_path[0]
            self.headers = {head.split(": ")[0]: head.split(": ")[1] for head in tmp[1:] if head != ''}
            if (self.logger):
                self.logger.debug(f"Headers retrived: {self.headers}")
            if ("Content-Length" in self.headers):
                self.data = await self.reader.read(int(self.headers["Content-Length"]))
                if (self.logger):
                    self.logger.debug(f"Data retrived: {self.data}")
            if (method == "GET"):
                self.do_GET()
            elif (method == "PUT"):
                put_th = Thread(target=self.do_PUT)
                put_th.start()
        except CloseException:
            self.close_event.set()
        except Exception as ex :
            self.logger.error(f"Exception: {ex}")
            html_file = html_template.format(title=pageTitle, content=ex)
            response_code = InternalServerError
            self.send_message(response_code, html_file)

    def __404__(self, do_get: Timer) -> None:
        if (self.logger):
            self.logger.debug("Sending 404 page.")
        _404_time = Timer()
        _404_file = ""
        if ("404" in TEMPLATES):
            _404_file = TEMPLATES["404"].format(title=pageTitle)
        else:
            _404_file = html_template.format(title=pageTitle, content="404 NOT FOUND")
        _404_time.stop()
        do_get.stop()
        self.send_message(NotFound, _404_file, f"full;dur={do_get}, process;dur={_404_time}")

    @staticmethod
    def render_static_file(name: str) -> bytes:
        data: Union[str, bytes] = STATIC[".".join(name.split(".")[:-1])]
        if (isinstance(data, str) and data.startswith("PATH")):
            _path = data.split("|")[-1]
            with open(path.join(cwd, _path), "r") as fp:
                data = fp.read()
        return data

    def send_message(self, response_code: ResponseCode, payload: Union[str, Dict[Any, Any], bytes], timing: str = "") -> None:
        if self.close_event.is_set(): return
        content_type = "text/html"
        if isinstance(payload, (dict)):
            content_type = "application/json"
            payload = dumps(payload)
        if isinstance(payload, bytes):
            content_type = "image/ico"
        if payload is None: payload = ""
        data = http_header.format(version_info=self.version, response_code=str(response_code), content_type=content_type, length=len(payload), timing=timing).encode()
        if (self.logger):
            self.logger.debug(f"Sending data: {data.decode()} with payload: {payload}")
        self.writer.write(data)
        self.writer.write(payload.encode() if not isinstance(payload, bytes) else payload)

    def do_GET(self) -> None:
        do_get = Timer()
        if (self.path in get_rules.keys()):
            get_rules_time = Timer()
            html_file = ""
            response_code: ResponseCode = None
            if (self.logger):
                self.logger.debug(f"Calling GET {self.path} with params: {self.path_params}")
            try:
                html_file = get_rules[self.path](self.path_params)
                response_code = Ok
            except KnownError as ke:
                html_file = html_template.format(title=pageTitle, content=ke.response.name)
                response_code = ke.response
                if (self.logger):
                    self.logger.warning(f"Known Exception: {ke}")
            except CloseException:
                self.close_event.set()
            except Exception as ex:
                html_file = html_template.format(title=pageTitle, content=ex)
                response_code = InternalServerError
                if (self.logger):
                    self.logger.error(f"Exception: {ex}")
            finally:
                if self.close_event.is_set():
                    self.writer.close()
                    return
                do_get.stop()
                get_rules_time.stop()
                self.send_message(response_code, html_file, f"full;dur={do_get}, process;dur={get_rules_time}")
                return
        if self.path.startswith("/static") or self.path == "/favicon.ico":
            if (self.logger):
                self.logger.debug(f"Serving static file from path: {self.path}")
            static = Timer()
            html_file = HTTPRequestHandler.render_static_file(self.path.split("/")[-1])
            if html_file is None:
                self.__404__(do_get)
                return
            static.stop()
            do_get.stop()
            self.send_message(Ok, html_file, f"full;dur={do_get}, process;dur={static}")
            return
        self.__404__(do_get)
    
    def do_PUT(self) -> None:
        do_put = Timer()
        if (self.path not in put_rules.keys()):
            self.__404__(do_put)
            return
        if (self.logger):
            self.logger.debug(f"Calling PUT {self.path}")
        message_return: ResponseCode = None
        try:
            put_rules[self.path](self.data)
            message_return = Ok
        except KnownError as ke:
            message_return = ke.response
            if (self.logger):
                self.logger.warning(f"Known Exception: {ke}")
        except CloseException:
                self.close_event.set()
        except Exception as ex:
            message_return = InternalServerError
            if (self.logger):
                self.logger.error(f"Exception: {ex}")
        finally:
            if self.close_event.is_set():
                self.writer.close()
                return
            do_put.stop()
            self.send_message(message_return, "", f"full={do_put}")

class HTMLServer:
    def __init__(self, host: str, port: int, root_path: str = ".", logger: Optional[Logger] = None, title: str = "HTML Server"):
        global pageTitle
        global cwd
        self.host = host
        self.port = port
        self.logger = logger
        self.handler: HTTPRequestHandler = HTTPRequestHandler
        self.server = None
        pageTitle = title
        cwd = root_path
        self.close_event = Event()

    def try_log(self, data: str, log_level: LEVEL = LEVEL.INFO) -> None:
        if self.logger == None:
            return
        self.logger.log(log_level, data)

    def render_template_file(self, name: str, **kwargs) -> str:
        data: str = TEMPLATES[name.replace(".html", "")]
        if (data.startswith("PATH")):
            _path = data.split("|")[-1]
            with open(path.join(cwd, _path), "r") as fp:
                data = fp.read()
        for template, value in kwargs.items():
            if isinstance(value, str):
                data = data.replace("{{ " + template + " }}", value)
            elif isinstance(value, list):
                items = self.render_template_list(template, value)
                data = data.replace("{{[ " + template + " ]}}", items)
        return data

    def render_template_list(self, name: str, values: List[str]) -> str:
        original = TEMPLATES[name]
        ret = []
        any_selected = False
        for val in values:
            vals = val.split('|')
            if len(vals) > 1 and vals[1] == "True": any_selected = True
            tmp = original.replace("{{VALUE}}", vals[0])
            tmp = tmp.replace("{{SELECTED}}", " selected" if len(vals) > 1 and vals[1] == "True" else "")
            ret.append(tmp)
        if ("option" in original):
            ret.insert(0, f"<option disabled{' selected' if not any_selected else ''} value></option>")
        return "\n".join(ret)

    def add_url_rule(self, rule: str, callback: Union[Callable[[Dict[str, str]], None], Callable[[bytes], None]], protocol: Protocol = Protocol.Get) -> None:
        if (protocol == Protocol.Get):
            get_rules[rule] = callback
        if (protocol == Protocol.Put):
            put_rules[rule] = callback

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        if self.close_event.is_set(): return
        addr = writer.get_extra_info('peername')
        self.try_log(f'Accepted connection from {addr[0]}:{addr[1]}')
        handler = self.handler(reader, writer, self.logger)
        await handler.handle_request()

    async def start(self):
        try:
            self.server = await asyncio.start_server(
                self.handle_client,
                self.host,
                self.port
            )
            self.try_log(f'Serving on {self.host}:{self.port}')
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            self.server = None

    def stop(self):
        try:
            self.try_log("Stopping server")
            if self.server:
                self.server.close()
                self.close_event.set()
        except Exception as ex:
            self.try_log(f"Exception stopping server: {ex}")

    def serve_forever_threaded(self, templates: Dict[str, str], static: Dict[str, str], thread_name: str = "SMDB HTTP Server") -> Thread:
        thread = Thread(target=self.serve_forever, args=[templates, static])
        thread.name = thread_name
        thread.start()
        return thread

    def serve_forever(self, templates: Dict[str, str], static: Dict[str, str]) -> None:
        for key, value in templates.items():
            TEMPLATES[key] = value
        for key, value in static.items():
            STATIC[key] = value
        asyncio.run(self.start())
