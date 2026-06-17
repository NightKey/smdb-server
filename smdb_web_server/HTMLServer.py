import asyncio
from threading import Event, Thread
from typing import Callable, Dict, Optional, Any, List, Coroutine, Union
from os import path

from smdb_logger import Logger, LEVEL

from smdb_web_server import HTTPRequestHandler, Protocol, UrlData, TEMPLATES, get_rules, put_rules, post_rules, STATIC, \
    async_wrapped, Base, wrapped, show_open_calls


class HTMLServer(Base):
    @property
    def logger(self) -> Logger:
        return self.__logger

    @property
    def name(self) -> str:
        return "HTMLServer"

    def __init__(
            self,
            host: str,
            port: int,
            root_path: str = ".",
            logger: Optional[Logger] = None,
            title: str = "HTML Server",
            disable_cache: bool = False,
            response_charset: str = "UTF-8",
            address_filter: Callable[[str], bool] = lambda _: True
    ):
        self.host = host
        self.port = port
        self.__logger = logger
        self.handler: HTTPRequestHandler = HTTPRequestHandler
        self.server: asyncio.Server = None
        self.pageTitle = title
        self.cwd = root_path
        self.close_event = Event()
        self.disable_cache = disable_cache
        self.charset = response_charset
        self.address_filter = address_filter
        self.server_task: asyncio.Task = None

    def try_log(self, data: str, log_level: LEVEL = LEVEL.INFO) -> None:
        if self.logger is None:
            return
        self.logger.log(log_level, data)

    @wrapped
    def render_template_file(self, name: str, **kwargs) -> str:
        data: str = TEMPLATES[name.replace(".html", "")]
        if data.startswith("PATH"):
            _path = data.split("|")[-1]
            with open(path.join(self.cwd, _path), "r", encoding=self.charset.lower()) as fp:
                data = fp.read()
        for template, value in kwargs.items():
            if isinstance(value, str):
                data = data.replace("{{ " + template + " }}", value)
            elif isinstance(value, list):
                items = self.render_template_list(template, value)
                data = data.replace("{{[ " + template + " ]}}", items)
        return data

    @staticmethod
    def render_template_list(name: str, values: List[str]) -> str:
        original = TEMPLATES[name]
        ret = []
        any_selected = False
        for val in values:
            vals = val.split('|')
            if len(vals) > 1 and vals[1] == "True": any_selected = True
            tmp = original.replace("{{VALUE}}", vals[0])
            tmp = tmp.replace("{{SELECTED}}", " selected" if len(vals) > 1 and vals[1] == "True" else "")
            ret.append(tmp)
        if "option" in original:
            ret.insert(0, f"<option disabled{' selected' if not any_selected else ''} value></option>")
        return "\n".join(ret)

    @staticmethod
    def add_url_rule(rule: str, callback: Union[Callable[[UrlData], str], Callable[[UrlData], Coroutine[Any, Any, str]]], protocol: Protocol = Protocol.Get, disable_cache: bool = False) -> None:
        if protocol == Protocol.Get:
            get_rules[rule] = (callback, disable_cache)
        elif protocol == Protocol.Put:
            put_rules[rule] = (callback, disable_cache)
        elif protocol == Protocol.Post:
            post_rules[rule] = (callback, disable_cache)

    @classmethod
    def as_url_rule(cls, rule: Optional[str] = None, protocol: Protocol = Protocol.Get, disable_cache: bool = False) -> Any:
        def decorator(callback: Union[Callable[[...], str], Callable[[...], Coroutine[Any, Any, str]]]):
            cls.add_url_rule(rule or callback.__name__, callback, protocol, disable_cache)
        return decorator

    @async_wrapped
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        if self.close_event.is_set(): return
        addr = writer.get_extra_info('peername')
        if not self.address_filter(addr[0]):
            self.try_log(f"Connection refused from {addr[0]}:{addr[1]}")
            writer.close()
            return
        self.try_log(f'Accepted connection from {addr[0]}:{addr[1]}')
        handler = self.handler(reader=reader, writer=writer, page_title=self.pageTitle, cwd=self.cwd, charset=self.charset, logger=self.logger, disable_cache=self.disable_cache)
        await handler.handle_request()

    @async_wrapped
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
                self.close_event.set()
                self.server.close()
                self.server_task.cancel()
        except Exception as ex:
            self.try_log(f"Exception stopping server: {ex}")
        finally:
            show_open_calls(self.logger.trace)

    @wrapped
    def serve_forever_threaded(self, templates: Dict[str, str], static: Dict[str, str], thread_name: str = "SMDB HTTP Server") -> Thread:
        """
        Starts the server on a different thread.
        **IMPORTANT**: This function will be removed.
        :param templates: Dictionary of path and value to be returned
        :param static: Dictionary of path and value to be returned
        :param thread_name: Default: SMDB HTTP Server
        :return: The thread created by this call
        """
        self.logger.warning("This function will be removed")
        thread = Thread(target=self.serve_forever, args=[templates, static])
        thread.name = thread_name
        thread.start()
        return thread

    @wrapped
    def serve_forever(self, templates: Dict[str, str], static: Dict[str, str]) -> None:
        """
        Starts the server and blocks the thread while it's running.
        **IMPORTANT**: This behavior will change to be non-blocking.
        :param templates: Dictionary of path and value to be returned
        :param static: Dictionary of path and value to be returned
        """
        self.logger.warning("This function will change to be non-blocking")
        for key, value in templates.items():
            TEMPLATES[key] = value
        for key, value in static.items():
            STATIC[key] = value
        loop = asyncio.new_event_loop()
        self.server_task = loop.create_task(self.start())
        while not self.server_task.done():
            loop.run_until_complete(asyncio.sleep(0.5))
