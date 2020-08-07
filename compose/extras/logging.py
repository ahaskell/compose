import inspect
import logging

from . import clsname


def get_logger_for_frame(frame_info):
    lname = None
    if frame_info is not None:
        lname = frame_info.function
        if lname == "<module>":
            lname = frame_info.frame.f_locals.get("__name__", None)
        if "self" in frame_info.frame.f_locals:
            lname = clsname(frame_info.frame.f_locals["self"], True) + "." + lname
    return logging.getLogger(lname)


class MagicLoggerType(type):

    def __getattribute__(self, item):
        if item == "__class__":
            return MagicLogger
        caller_local = {}
        frame_info = None
        stack = inspect.stack()
        for frame_info in stack[1:]:
            if frame_info.frame.f_locals.get("self", None):
                caller_local = frame_info.frame.f_locals
                break
        caller_local["logger"] = get_logger_for_frame(frame_info)
        return getattr(caller_local["logger"], item)


class MagicLogger(metaclass=MagicLoggerType):
    pass


DEBUG = True
logger = logging.getLogger("compose")
if DEBUG:
    logger = MagicLogger
