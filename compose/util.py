from typing import Generic

from .extras import Undefined


def walk(start_point, yielder):
    current_point = start_point
    while current_point not in (None, Undefined):
        yield current_point
        try:
            current_point = yielder(current_point)
        except AttributeError:
            break


def is_resolvable(kls):
    from typing import _GenericAlias
    return isinstance(kls, (type, Generic, _GenericAlias))