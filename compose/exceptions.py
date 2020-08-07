import sys
import traceback
from collections import OrderedDict
from contextlib import redirect_stdout

from .extras import ascls, LocationInfo
from .extras.logging import logger
from .extras.undef import Undefined
from .util import walk


class ComposeError(Exception):
    def __init__(self, msg, location=None):
        self.locations = source_pointer(location)
        super().__init__(msg)

    def __str__(self):
        msg = [super().__str__()]
        if len(self.locations):
            msg.append(" ")
            msg.append("In addition to the stack trace the source of the could be in the following locations:")
        for loc in self.locations:
            msg.append(str(loc))
        return "\n".join(msg)


class InstantiationError(ComposeError):
    def __init__(self, msg, context: 'InstantiationContext', location=None):
        self.target = context.target
        self.context = context
        self.locations = source_pointer(location)
        super().__init__(msg, location=location)


class DependencyError(InstantiationError):
    pass


class ContractFailure(DependencyError):
    def __init__(self, msg, key, key_type, context: 'InstantiationContext', location=None):
        self.key = key
        self.key_type = key_type
        self.context = context
        self.locations = source_pointer(location)
        super().__init__(msg, context, location=location)


class AmbiguousDependency(DependencyError):
    pass


class TooManyProviders(DependencyError):
    def __init__(self, msg, sourced, context, location=None):
        super().__init__(msg, context, location=location)
        self._sourced = sourced


class RequirementNotFound(DependencyError):
    def __init__(self, msg, failed_arg, context, location=None):
        super().__init__(msg, context, location=location)
        self.target = failed_arg


class InvalidBindType(DependencyError):
    pass


def source_pointer(locations):
    loc_infos = []
    if locations is None:
        return loc_infos
    if not isinstance(locations, list):
        locations = [locations]
    for location in locations:
        location = ascls(location)
        loc_infos.append(LocationInfo(location))
    return loc_infos


class OptionalRequirementNotFound(RequirementNotFound):
    pass


def compose_exception_printer(a, b, c, d=None):
    if isinstance(b, InstantiationError):
        locations = []
        provider_bundles = set()
        instantiation_stack = OrderedDict()
        indent_size = 4
        last_compost_error = Undefined
        with redirect_stdout(sys.stderr):
            print("Compose Error Found\n")
            for layer in walk(b, lambda err: err.__cause__):
                if not isinstance(layer, InstantiationError):
                    traceback.print_exception(type(layer), layer, layer.__traceback__)
                    print("Real Error: ", layer)
                    continue
                last_compost_error = layer
                provider_bundles.update(layer.context.compose._bundles)
                locations.extend(layer.locations)
            from .context import print_context
            print_context(last_compost_error.context)
            print(layer)
            print("\n\nBundles used:")
            for pb in provider_bundles:
                print(" " * indent_size + LocationInfo(pb))
            print("\nAdditional Paths:")
            for loc in locations:
                print(" " * indent_size + loc)
    else:
        sys.__excepthook__(a, b, c)


sys.excepthook = compose_exception_printer
try:
    pydevd = sys.modules["pydevd"]
    logger.warning("pydev found, which most likely means debugging is instrumented. "
                   "There is a bug in pydev that prevents Compose from hooking into exceptions so Compose exceptions "
                   "will look different and may be harder to understand")
except Exception:
    pass
