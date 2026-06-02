import asyncio
from asyncio import iscoroutinefunction
from json import dumps
from threading import Event
from typing import Dict, Union, Any
from os import path

from smdb_web_server import Timer, ResponseCode, UrlData, CloseException, Constants, KnownError, TEMPLATES, STATIC, \
    get_rules, put_rules, post_rules

from smdb_logger import Logger, LEVEL

page_title: str = ""
charset: str = ""
cwd: str = "."

class HTTPRequestHandler:
    html_template: str = "<html><head><link rel='stylesheet' href='/static/style.css' /><title>{title}</title></head><body>{content}</body></html>"
    http_header: str = "{version_info} {response_code}\r\nContent-Length: {length}\r\nContent-Type: {content_type}{cache_control};\r\nServer-Timing: {timing}\r\n\r\n"
    cache_disabled_addition: str = "\r\nCache-Control: no-store, must-revalidate\r\nPragma: no-cache\r\nExpires: 0"

    def __init__(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
            page_title: str,
            cwd: str,
            charset: str,
            logger: Logger = None,
            disable_cache: bool = False,
            source_address: str = ""
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.page_title: str = page_title
        self.cwd: str = cwd
        self.charset: str = charset
        self.headers: Dict[str, str] = None
        self.path: str = ""
        self.data: UrlData = None
        self.version: str = "HTTP/1.0"
        self.logger = logger
        self.close_event = Event()
        self.disable_cache = disable_cache
        self.source_address = source_address
        # For static rendering
        globals()["pageTitle"] = self.page_title
        globals()["charset"] = self.charset
        globals()["cwd"] = self.cwd


    async def handle_request(self):
        try:
            tmp = await self.reader.readuntil("\r\n\r\n".encode())
            tmp = tmp.decode().split("\r\n")
            method, tmp_path, _ = tmp[0].split(" ")
            tmp_path = tmp_path.split("#")
            fragment = None
            if len(tmp_path) > 1:
                fragment = tmp_path[-1]
            tmp_path = tmp_path[0]
            tmp_path = tmp_path.split("?")
            query = None
            if len(tmp_path) > 1:
                query = self.getQueryItems(tmp_path[-1])
            self.path = tmp_path[0]
            self.headers = {head.split(": ")[0]: head.split(": ")[1] for head in tmp[1:] if head != ''}
            if self.logger:
                self.logger.debug(f"Headers retried: {self.headers}")
            data = None
            if "Content-Length" in self.headers:
                data = await self.reader.read(int(self.headers["Content-Length"]))
                if self.logger:
                    self.logger.trace(f"Data retried: {data}")
            self.data = UrlData(query, fragment, data, self.source_address, self.headers)
            self.logger.info(f"Serving request from {self.source_address} with data: {self.data} and with path: {self.path}")
            if method == "GET":
                await self.do_GET()
            elif method == "PUT":
                await self.do_PUT()
            elif method == "POST":
                await self.do_POST()
        except CloseException:
            self.close_event.set()
        except Exception as ex:
            self.logger.error(f"Exception during handling request a request", ex)
            html_file = HTTPRequestHandler.html_template.format(title=self.page_title, content=ex)
            response_code = Constants.InternalServerError
            self.send_message(response_code, html_file)

    def getQueryItems(self, items: str) -> Dict[str, Any]:
        ret = {}
        for item in items.split("&"):
            if len(item.split("=")) == 2:
                ret[item.split("=")[0]] = item.split("=")[1]
            else:
                ret[item] = None
        return ret

    def __404__(self, do_get: Timer) -> None:
        if self.logger:
            self.logger.debug("Sending 404 page.")
        _404_time = Timer()
        _404_file = ""
        if "404" in TEMPLATES:
            _404_file = TEMPLATES["404"].format(title=self.page_title)
        else:
            _404_file = HTTPRequestHandler.html_template.format(title=self.page_title, content="404 NOT FOUND")
        _404_time.stop()
        do_get.stop()
        self.send_message(Constants.NotFound, _404_file, f"full;dur={do_get}, process;dur={_404_time}")

    @staticmethod
    def render_static_file(name: str) -> bytes:
        data: Union[str, bytes] = STATIC.get(".".join(name.split(".")[:-1]), None)
        if isinstance(data, str) and data.startswith("PATH"):
            _path = data.split("|")[-1]
            read_mode = "rb" if (_path.split(".")[-1] in ["jpg", "png", "ico", "mp3", "mp4", "wav"]) else "r"
            with open(path.join(cwd, _path), read_mode, encoding="" if (read_mode == "rb") else charset) as fp:
                data = fp.read()
        return data

    def send_message(
            self,
            response_code: ResponseCode,
            payload: Union[str, Dict[Any, Any], bytes],
            timing: str = ""
    ) -> None:
        if self.close_event.is_set(): return
        content_type = f"text/html;charset={self.charset}"
        if isinstance(payload, dict):
            content_type = f"application/json;charset={self.charset}"
            payload = dumps(payload)
        if isinstance(payload, bytes):
            content_type = "image/ico"
        if "css" in self.path:
            content_type = "text/css"
        if "js" in self.path:
            content_type = "text/javascript"
        if payload is None: payload = ""
        cache_control = HTTPRequestHandler.cache_disabled_addition if self.disable_cache else ""
        data = HTTPRequestHandler.http_header.format(
            version_info=self.version,
            response_code=str(response_code),
            content_type=content_type,
            cache_control=cache_control,
            length=len(payload),
            timing=timing
        )
        if self.logger:
            self.logger.trace(f"Sending data: {data} with payload: {payload}")
        self.writer.write(data.encode())
        self.writer.write(payload.encode() if not isinstance(payload, bytes) else payload)

    async def do_GET(self) -> None:
        do_get = Timer()
        if self.path in get_rules.keys():
            get_rules_time = Timer()
            html_file = ""
            response_code: ResponseCode = None
            if self.logger:
                self.logger.debug(f"Calling GET {self.path} with params: {self.data}")
            try:
                callback = get_rules[self.path][0]
                if iscoroutinefunction(callback):
                    html_file = await callback(self.data)
                else:
                    html_file = callback(self.data)
                response_code = Constants.Ok
                self.disable_cache = get_rules[self.path][1] or self.disable_cache
            except KnownError as ke:
                html_file = HTTPRequestHandler.html_template.format(title=self.page_title, content=ke.response.name)
                response_code = ke.response
                if self.logger:
                    self.logger.warning(f"Known Exception: {ke}")
            except CloseException:
                self.close_event.set()
            except Exception as ex:
                html_file = HTTPRequestHandler.html_template.format(title=self.page_title, content=ex)
                response_code = Constants.InternalServerError
                if self.logger:
                    self.logger.error(f"Exception during handling a GET request for {self.path}", ex)
            finally:
                if self.close_event.is_set():
                    self.writer.close()
                else:
                    do_get.stop()
                    get_rules_time.stop()
                    self.send_message(response_code, html_file, f"full;dur={do_get}, process;dur={get_rules_time}")
            return

        if self.path.startswith("/static") or self.path == "/favicon.ico":
            if self.logger:
                self.logger.debug(f"Serving static file from path: {self.path}")
            static = Timer()
            html_file = HTTPRequestHandler.render_static_file(self.path.split("/")[-1])
            if html_file is None:
                self.__404__(do_get)
                return
            static.stop()
            do_get.stop()
            self.send_message(Constants.Ok, html_file, f"full;dur={do_get}, process;dur={static}")
            return

        self.__404__(do_get)

    async def do_PUT(self) -> None:
        do_put = Timer()
        if self.path not in put_rules.keys():
            self.__404__(do_put)
            return
        if self.logger:
            self.logger.debug(f"Calling PUT {self.path}")
        message_return: ResponseCode = None
        result = ""
        try:
            callback = put_rules[self.path][0]
            result = None
            if iscoroutinefunction(callback):
                result = await callback(self.data)
            else:
                result = callback(self.data)
            self.disable_cache = put_rules[self.path][1] or self.disable_cache
        except KnownError as ke:
            message_return = ke.response
            if self.logger:
                self.logger.warning(f"Known Exception: {ke}")
        except CloseException:
            self.close_event.set()
        except Exception as ex:
            message_return = Constants.InternalServerError
            if self.logger:
                self.logger.error(f"Exception during handling a PUT request for {self.path}", ex)
        finally:
            if self.close_event.is_set():
                self.writer.close()
            else:
                do_put.stop()
                self.send_message(message_return, result, f"full={do_put}")

    async def do_POST(self) -> None:
        do_post = Timer()
        if self.path not in post_rules.keys():
            self.__404__(do_post)
            return
        if self.logger:
            self.logger.debug(f"Calling POST {self.path}")
        message_return: ResponseCode = None
        result = ""
        try:
            callback = post_rules[self.path][0]
            result = None
            if iscoroutinefunction(callback):
                result = await callback(self.data)
            else:
                result = callback(self.data)
            message_return = Constants.Ok
            self.disable_cache = post_rules[self.path][1] or self.disable_cache
        except KnownError as ke:
            message_return = ke.response
            if self.logger:
                self.logger.warning(f"Known Exception: {ke}")
        except CloseException:
            self.close_event.set()
        except Exception as ex:
            message_return = Constants.InternalServerError
            if self.logger:
                self.logger.error(f"Exception during handling a POST request for {self.path}", ex)
        finally:
            if self.close_event.is_set():
                self.writer.close()
            else:
                do_post.stop()
                self.send_message(message_return, result, f"full={do_post}")
