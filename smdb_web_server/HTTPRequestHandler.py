import asyncio
import inspect
from json import dumps
from threading import Event
from typing import Dict, Union, Any, Callable, List

from smdb_web_server import Timer, ResponseCode, UrlData, CloseException, Constants, KnownError, TEMPLATES, STATIC, \
    get_rules, put_rules, post_rules, async_wrapped, Base, wrapped, show_open_calls, RequestException

from smdb_logger import Logger, LEVEL


class HTTPRequestHandler(Base):
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
            logger: Union[Logger, None] = None,
            disable_cache: bool = False,
            source_address: str = "",
            source_filter: Callable[[str], bool] = lambda _: True
    ) -> None:
        super().__init__(
            logger=logger,
            cwd=cwd,
            charset=charset
        )
        self.reader = reader
        self.writer = writer
        self.page_title: str = page_title
        self.path: str = ""
        self.data: Union[UrlData, None] = None
        self.version: str = "HTTP/1.0"
        self.close_event = Event()
        self.disable_cache = disable_cache
        self.source_address = source_address
        self.source_filter = source_filter

    @async_wrapped
    async def handle_request(self):
        try:
            tmp = await self.reader.readuntil("\r\n\r\n".encode())
            tmp = tmp.decode().split("\r\n")
            method, tmp_path, _ = tmp[0].split(" ")
            tmp_path = tmp_path.split("#")
            fragment = ""
            if len(tmp_path) > 1:
                fragment = tmp_path[-1]
            tmp_path = tmp_path[0]
            tmp_path = tmp_path.split("?")
            query = {}
            if len(tmp_path) > 1:
                query = self.get_query_items(tmp_path[-1])
            self.path = tmp_path[0]
            headers = {head.split(": ")[0]: head.split(": ")[1] for head in tmp[1:] if head != ''}
            if "Forwarded" in headers.keys() and not await self.proxy_user_allowed(headers["Forwarded"].split(";")): return
            self.try_log(message=f"Headers retried: {headers}", level=LEVEL.DEBUG)
            data = b''
            if "Content-Length" in headers:
                data = await self.reader.read(int(headers["Content-Length"]))
                self.try_log(message=f"Data retried: {data}", level=LEVEL.TRACE)
            self.data = UrlData(query, fragment, data, self.source_address, headers)
            self.try_log(message=f"Serving request from {self.source_address} with data: {self.data} and with path: {self.path}")
            if method == "GET":
                await self.do_GET()
            elif method == "PUT":
                await self.do_PUT()
            elif method == "POST":
                await self.do_POST()
        except CloseException:
            await self.cleanup()
        except Exception as ex:
            self.try_log(message=f"Exception during handling request a request", exception=ex, level=LEVEL.ERROR)
            html_file = HTTPRequestHandler.html_template.format(title=self.page_title, content=ex)
            response_code = Constants.InternalServerError
            self.send_message(response_code, html_file)
        finally:
            show_open_calls(self.try_trace)

    @async_wrapped
    async def proxy_user_allowed(self, forward_headers: List[str]) -> bool:
        for f_header in forward_headers:
            (key, value) = f_header.split("=")
            if key == "for" and not self.source_filter(value):
                self.try_log(message=f"IP address {value} was refused by source filter")
                html_file = HTTPRequestHandler.html_template.format(title=self.page_title,content="IP your IP address is not allowed")
                response_code = Constants.Forbidden
                self.send_message(response_code, html_file)
                await self.cleanup()
                return False
        else:
            return True

    @wrapped
    def get_query_items(self, items: str) -> Dict[str, str]:
        ret = {}
        for item in items.split("&"):
            if len(item.split("=")) == 2:
                ret[item.split("=")[0]] = item.split("=")[1]
            else:
                ret[item] = ""
        return ret

    def __404__(self, do_get: Timer) -> None:
        self.try_log(message="Sending 404 page.", level=LEVEL.DEBUG)
        _404_time = Timer()
        _404_file = ""
        if "404" in TEMPLATES:
            _404_file = TEMPLATES["404"].format(title=self.page_title)
        else:
            _404_file = HTTPRequestHandler.html_template.format(title=self.page_title, content="404 NOT FOUND")
        _404_time.stop()
        do_get.stop()
        self.send_message(Constants.NotFound, _404_file, f"full;dur={do_get}, process;dur={_404_time}")

    def render_static_file(self, name: str) -> Union[str, bytes, None]:
        return super().__render_static_file(name=name, STATIC=STATIC)

    @wrapped
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
            content_type = f"text/css;charset={self.charset}"
        if "js" in self.path:
            content_type = f"text/javascript;charset={self.charset}"
        if payload is None: payload = ""
        cache_control = HTTPRequestHandler.cache_disabled_addition if self.disable_cache else ""
        data = HTTPRequestHandler.http_header.format(
            version_info=self.version,
            response_code=str(response_code),
            content_type=content_type,
            cache_control=cache_control,
            length=len(payload) if isinstance(payload, bytes) else len(payload.encode(encoding=self.charset)),
            timing=timing
        )
        self.try_log(message=f"Sending data: {data} with payload: {payload}", level=LEVEL.TRACE)
        self.writer.write(data.encode())
        self.writer.write(payload.encode() if not isinstance(payload, bytes) else payload)

    @async_wrapped
    async def do_GET(self) -> None:
        do_get = Timer()
        if self.path in get_rules.keys():
            get_rules_time = Timer()
            html_file = ""
            response_code: ResponseCode = Constants.InternalServerError
            self.try_log(message=f"Calling GET {self.path} with params: {self.data}", level=LEVEL.DEBUG)
            try:
                if self.data is None:
                    raise RequestException(f"GET request does not have data: {self.path}")
                callback = get_rules[self.path][0]
                if inspect.iscoroutinefunction(callback):
                    html_file = await callback(self.data)
                else:
                    html_file = callback(self.data)
                response_code = Constants.Ok
                self.disable_cache = get_rules[self.path][1] or self.disable_cache
            except KnownError as ke:
                html_file = self.html_template.format(title=self.page_title, content=ke.response.name)
                response_code = ke.response
                self.try_log(message=f"Known Exception: {ke}", level=LEVEL.WARNING)
            except CloseException:
                await self.cleanup()
            except RequestException as rex:
                html_file = self.html_template.format(title=self.page_title, content=rex)
                response_code = Constants.BadRequest
                self.try_log(message=f"Request Exception: {rex}", level=LEVEL.WARNING)
            except Exception as ex:
                html_file = self.html_template.format(title=self.page_title, content=ex)
                self.try_log(message=f"Exception during handling a GET request for {self.path}", exception=ex, level=LEVEL.ERROR)
            finally:
                if not self.close_event.is_set():
                    do_get.stop()
                    get_rules_time.stop()
                    self.send_message(response_code, html_file, f"full;dur={do_get}, process;dur={get_rules_time}")
            return

        if self.path.startswith("/static") or self.path == "/favicon.ico":
            self.try_log(message=f"Serving static file from path: {self.path}", level=LEVEL.DEBUG)
            static = Timer()
            html_file = self.render_static_file(self.path.split("/")[-1])
            if html_file is None:
                self.__404__(do_get)
                return
            static.stop()
            do_get.stop()
            self.send_message(Constants.Ok, html_file, f"full;dur={do_get}, process;dur={static}")
            return

        self.__404__(do_get)

    @async_wrapped
    async def do_PUT(self) -> None:
        do_put = Timer()
        if self.path not in put_rules.keys():
            self.__404__(do_put)
            return
        self.try_log(message=f"Calling PUT {self.path}", level=LEVEL.DEBUG)
        message_return: ResponseCode = Constants.InternalServerError
        result = ""
        try:
            if self.data is None:
                raise RequestException(f"PUT request does not have data: {self.path}")
            callback = put_rules[self.path][0]
            if inspect.iscoroutinefunction(callback):
                result = await callback(self.data)
            else:
                result = callback(self.data)
            self.disable_cache = put_rules[self.path][1] or self.disable_cache
        except KnownError as ke:
            message_return = ke.response
            self.try_log(message=f"Known Exception: {ke}", level=LEVEL.WARNING)
        except CloseException:
            await self.cleanup()
        except RequestException as rex:
            result = self.html_template.format(title=self.page_title, content=rex)
            message_return = Constants.BadRequest
            self.try_log(message=f"Request Exception: {rex}", level=LEVEL.WARNING)
        except Exception as ex:
            message_return = Constants.InternalServerError
            self.try_log(message=f"Exception during handling a PUT request for {self.path}", exception=ex, level=LEVEL.ERROR)
        finally:
            if not self.close_event.is_set():
                do_put.stop()
                self.send_message(message_return, result, f"full={do_put}")

    @async_wrapped
    async def do_POST(self) -> None:
        do_post = Timer()
        if self.path not in post_rules.keys():
            self.__404__(do_post)
            return
        self.try_log(message=f"Calling POST {self.path}", level=LEVEL.DEBUG)
        message_return: ResponseCode = Constants.InternalServerError
        result = ""
        try:
            if self.data is None:
                raise RequestException(f"POST request does not have data: {self.path}")
            callback = post_rules[self.path][0]
            if inspect.iscoroutinefunction(callback):
                result = await callback(self.data)
            else:
                result = callback(self.data)
            message_return = Constants.Ok
            self.disable_cache = post_rules[self.path][1] or self.disable_cache
        except KnownError as ke:
            message_return = ke.response
            self.try_log(message=f"Known Exception: {ke}", level=LEVEL.WARNING)
        except CloseException:
            await self.cleanup()
        except RequestException as rex:
            result = self.html_template.format(title=self.page_title, content=rex)
            message_return = Constants.BadRequest
            self.try_log(message=f"Request Exception: {rex}", level=LEVEL.WARNING)
        except Exception as ex:
            message_return = Constants.InternalServerError
            self.try_log(message=f"Exception during handling a POST request for {self.path}", exception=ex, level=LEVEL.ERROR)
        finally:
            if not self.close_event.is_set():
                do_post.stop()
                self.send_message(message_return, result, f"full={do_post}")

    @async_wrapped
    async def cleanup(self) -> None:
        self.close_event.set()
        self.writer.close()
