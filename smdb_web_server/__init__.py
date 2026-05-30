from typing import Dict, Tuple, Callable, Union, Coroutine, Any

from .data import *
from .errors import *

get_rules: Dict[str, Tuple[Union[Callable[[UrlData], str], Callable[[UrlData], Coroutine[Any, Any, str]]], bool]] = {}
put_rules: Dict[str, Tuple[Union[Callable[[UrlData], str], Callable[[UrlData], Coroutine[Any, Any, str]]], bool]] = {}
post_rules: Dict[str, Tuple[Union[Callable[[UrlData], str], Callable[[UrlData], Coroutine[Any, Any, str]]], bool]] = {}
TEMPLATES: Dict[str, str] = {}
STATIC: Dict[str, str] = {}

from .HTTPRequestHandler import HTTPRequestHandler
from .HTMLServer import HTMLServer
