from abc import ABC, abstractmethod

from smdb_logger import Logger


class Base(ABC):
    @property
    @abstractmethod
    def logger(self) -> Logger:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
