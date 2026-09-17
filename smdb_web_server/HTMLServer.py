import asyncio
from threading import Event, Thread
from typing import Callable, Dict, Optional, Any, List, Coroutine, Union
from os import path

from smdb_logger import Logger, LEVEL

from smdb_web_server import HTTPRequestHandler, Protocol, UrlData, TEMPLATES, get_rules, put_rules, post_rules, STATIC, \
    async_wrapped, Base, wrapped, show_open_calls


class HTMLServer(Base):
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
        super().__init__(
            logger=logger,
            cwd=root_path,
            charset=response_charset
        )
        self.host = host
        self.port = port
        self.server: Union[asyncio.Server, None] = None
        self.pageTitle = title
        self.close_event = Event()
        self.disable_cache = disable_cache
        self.address_filter = address_filter
        self.server_task: Union[asyncio.Task, None] = None

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

    def render_static_file(self, name: str) -> Union[str, bytes, None]:
        return self._render_static_file(name=name, STATIC=STATIC)

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
            self.try_log(message=f"Connection from {addr[0]}:{addr[1]} refused")
            writer.close()
            return
        self.try_log(message=f'Accepted connection from {addr[0]}:{addr[1]}')
        handler = HTTPRequestHandler(reader=reader, writer=writer, page_title=self.pageTitle, cwd=self.cwd, charset=self.charset, logger=self.logger, disable_cache=self.disable_cache)
        await handler.handle_request()

    @async_wrapped
    async def start(self):
        try:
            self.server = await asyncio.start_server(
                self.handle_client,
                self.host,
                self.port
            )
            self.try_log(message=f'Serving on {self.host}:{self.port}')
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            self.server = None

    def stop(self):
        try:
            self.try_log(message="Stopping server")
            if self.server:
                self.close_event.set()
                self.server.close()
                self.server_task.cancel()
        except Exception as ex:
            self.try_log(message=f"Exception stopping server", exception=ex, level=LEVEL.ERROR)
        finally:
            show_open_calls(self.logger.trace)

    @wrapped
    def serve_forever_threaded(self, templates: Dict[str, str], static: Dict[str, str], thread_name: str = "SMDB HTTP Server") -> Thread:
        """
        Starts the server on a different thread.
        :param templates: Dictionary of path and value to be returned
        :param static: Dictionary of path and value to be returned
        :param thread_name: Default: SMDB HTTP Server
        :return: The thread created by this call
        """
        thread = Thread(target=self.serve_forever, args=[templates, static])
        thread.name = thread_name
        thread.start()
        return thread

    @wrapped
    def serve_forever(self, templates: Dict[str, str], static: Dict[str, str]) -> None:
        """
        Starts the server and blocks the thread while it's running.
        :param templates: Dictionary of path and value to be returned
        :param static: Dictionary of path and value to be returned
        """
        for key, value in templates.items():
            TEMPLATES[key] = value
        for key, value in static.items():
            STATIC[key] = value
        loop = asyncio.new_event_loop()
        self.server_task = loop.create_task(self.start())
        while not self.server_task.done():
            loop.run_until_complete(asyncio.sleep(0.5))
