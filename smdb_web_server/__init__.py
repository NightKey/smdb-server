from typing import Dict, Tuple, Callable

from .data import *
from .errors import *

get_rules: Dict[str, Tuple[Callable[[Dict[str, str]], str], bool]] = {}
put_rules: Dict[str, Tuple[Callable[[bytes], str], bool]] = {}
post_rules: Dict[str, Tuple[Callable[[bytes], str], bool]] = {}
TEMPLATES: Dict[str, str] = {}
STATIC: Dict[str, str] = {}

from .HTTPRequestHandler import HTTPRequestHandler
from .HTMLServer import HTMLServer
