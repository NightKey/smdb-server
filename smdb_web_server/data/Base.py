from abc import ABC, abstractmethod
from os import path
from typing import Union, Dict

from smdb_logger import Logger, LEVEL


class Base(ABC):

    def __init__(
            self,
            logger: Union[Logger, None],
            cwd: str,
            charset: str
    ) -> None:
        self.logger = logger
        self.name = type(self).__name__
        self.cwd = cwd
        self.charset = charset

    def try_log(self, *, message: str, exception: Union[Exception, None] = None, level: LEVEL = LEVEL.INFO) -> None:
        if self.logger is not None:
            self.logger.log(level=level, data=message, exception=exception)

    def try_trace(self, message: str) -> None:
        self.try_log(message=message, exception=None, level=LEVEL.TRACE)

    def _render_static_file(self, name: str, STATIC: Dict[str, str] ) -> Union[str, bytes, None]:
        parsed_name = ".".join(name.split(".")[:-1]) or name
        data: Union[str, bytes, None] = STATIC.get(parsed_name, None)
        if isinstance(data, str) and data.startswith("PATH"):
            _path = data.split("|")[-1]
            read_mode = "rb" if (_path.split(".")[-1] in ["jpg", "png", "ico", "mp3", "mp4", "wav"]) else "r"
            with open(path.join(self.cwd, _path), read_mode, encoding="" if (read_mode == "rb") else self.charset) as fp:
                data = fp.read()
        return data
