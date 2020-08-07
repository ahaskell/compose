import inspect

from .generics import *
from .undef import *

__all__ = [
    'LocationInfo',
    'clsname',
    'ascls']
__all__.extend(undef.__all__)
__all__.extend(generics.__all__)


class LocationInfo(str):

    def __new__(cls, obj, full_name=True, **kwargs):
        if obj is None:
            return super().__new__(cls, "None has no Locatioin")
        obj_cls = ascls(obj)
        file_location = inspect.getsourcefile(obj_cls)
        source_code, line_no = inspect.findsource(obj_cls)
        line_no += 1
        object_name = clsname(obj_cls, full=full_name)
        v = f'{object_name} File "{file_location}", line {line_no} '
        new_str = super().__new__(cls, v)
        new_str.reference_point = ascls(obj)
        new_str.path = file_location
        new_str.line_no = line_no
        new_str.source_code = source_code
        new_str.object_name = object_name
        return new_str


def clsname(maybe_cls, full=False):
    kls = ascls(maybe_cls)
    name_parts = []
    if full:
        name_parts.append(kls.__module__)
    name_parts.append(kls.__name__)
    return ".".join(name_parts)


def ascls(maybe_cls):
    """Sometimes code wants the class but is given an object. ascls just takes that small piece of logic and provides
    a clean method call to ensure the code is working on a class not an instance.


    :param Any maybe_cls:
    :return: Type
    """
    cls = maybe_cls
    if not isinstance(maybe_cls, type):
        cls = maybe_cls.__class__
    return cls
