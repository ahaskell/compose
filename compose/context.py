import inspect
import sys
import traceback
from dataclasses import dataclass, field, fields
from functools import partial
from itertools import chain
from typing import Type, Text

from .exceptions import DependencyError, InstantiationError, OptionalRequirementNotFound, ContractFailure, \
    InvalidBindType, ComposeError, RequirementNotFound, TooManyProviders
from .extras import clsname, LocationInfo
from .extras.generics import *
from .extras.logging import logger
from .extras.undef import Undefined, is_defined
from .modifiers import Required, Lazy
from .proxying import LazyProxy
from .util import is_resolvable, walk


@dataclass
class InstantiationContext(object):
    target: Type
    parent: 'InstantiationContext'
    compose: 'Compose'

    _provider = None
    _lazy: bool = False
    resolving_key: Text = field(init=False, default=Undefined)
    resolving_type: Type = field(init=False, default=Undefined)

    @property
    def is_root(self):
        return self.parent is Undefined

    @property
    def provider(self) -> 'Binding':
        return self._provider

    @provider.setter
    def provider(self, v: 'Binding'):
        self._provider = v

    @property
    def instance(self):
        if self._provider.is_singleton:
            return self._provider.factory()
        try:
            obj = self.call_method(self._provider.factory)
            if hasattr(obj, "requires"):
                self.call_method(obj.requires, default_required=True)
            if hasattr(obj, "accepts"):
                self.call_method(obj.accepts, default_required=False)
            if self._provider._as_singleton:
                self._provider._factory = lambda: obj
                self._provider.is_singleton = True
            return obj
        except DependencyError as ex:
            raise InstantiationError(f"Unable to Instantiate {self._provider._config_for}, ", self) from ex
        except InstantiationError as ex:
            raise InstantiationError(f"Unable to Instantiate {self._provider._config_for}", self) from ex
        except Exception as ex:
            raise InstantiationError(f"Unable to Instantiate {self._provider._config_for}", self) from ex

    def call_method(self, method, default_required: bool = Undefined):
        kwargs = {}
        args = []
        signature = None

        try:
            signature = inspect.signature(method)
        except ValueError:
            # if there is nothing to inspect inspect.signature throws ValueError
            pass
        optional = not default_required if is_defined(default_required) else Undefined
        if signature:
            for k, param in signature.parameters.items():
                if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    continue
                self.resolving_key = k
                default_provided = param.default not in (param.empty, Required)

                param_optional = is_optional(param.annotation) or optional or default_provided

                try:
                    arg_value = self.resolve_arg(param.annotation)
                except OptionalRequirementNotFound:
                    logger.debug(f"Optional dependency for {k} not found. Type: {param.annotation}")
                    if param.kind == inspect.Parameter.POSITIONAL_ONLY:
                        value = param.default or None
                        logger.warning(f"Optional dependency not found position onluy parameter {k}. "
                                       f"Using value {value}")
                        args.append(param.default or None)
                except InstantiationError as ex:
                    if not param_optional:
                        raise ContractFailure(f"Unable to fulfill contract for {k}:{param.annotation}",
                                              key=k, key_type=param.annotation,
                                              context=self,
                                              location=method) from ex
                    else:
                        if not default_provided and param_optional:
                            args.append(None)
                        # don't log optional InvalidBindType since they can't ever be resolved.
                        if not isinstance(ex, InvalidBindType):
                            logger.debug(f"Optional dependency not resolved {k}:{param.annotation}")
                else:
                    if param.kind == inspect.Parameter.POSITIONAL_ONLY:
                        args.append(arg_value)
                    else:
                        kwargs[k] = arg_value

            logger.debug(f"Calling {method} with {kwargs.keys()}")
        try:
            obj = method(*args, **kwargs)
        except TypeError as ex:
            ex_type, ex_ex, ex_tb = sys.exc_info()
            traceback.print_tb(ex_tb)
            if isinstance(method, partial):
                try:
                    name = f"(Partial){method.func.__name__}"
                except AttributeError:
                    name = f"Some Partial {method}"
            else:
                try:
                    name = method.__name__
                except:
                    name = method

            try:
                msg = f"Well this should not happen. Something in the signature is required but " \
                      f"Compose is not providing.\n{ex} \nApproximation of what was called: \n" \
                      f"{name}({','.join(list(chain(list(str(i) for i in args), list('='.join(str(i) for i in arg) for arg in kwargs.items()))))})\n" \
                      f"Troubleshooting  info:\n {param}"
            except:
                msg = "Compose has an unchecked issue. Generally this is because the signature requires something " \
                      "that is not being provided by compose and then Compose could not generate a useful message" \
                      f"This is the resulting message. \n Troubleshooting  info:\n {param}"
            raise ComposeError(msg, location=method) from ex

        return obj

    def lazy_resolve(self, ):
        self.resolve(self.target)

    def resolve(self, kls, lazy=False):
        self.resolving_type = kls
        context = self.__class__(kls, self, self.compose, _lazy=lazy)
        resolved = list(self.compose.provide_all(kls, context))
        if is_defined(resolved):
            return resolved

    def resolve_arg(self, arg, lazy=False):
        items = []
        if arg is None:
            return items
        if not is_resolvable(arg):
            logger.warning(f"Using a {type(arg)} as a datatype will probably have dire consequences")
        elif not self.is_supported(arg):
            raise InvalidBindType(f"Requirement of parameter type {arg} found. Compose can not provide these.",
                                  context=self)

        optional = is_optional(arg)
        # Special cases for certain generic classes
        origin = get_origin(arg)
        if lazy or origin is Lazy:
            arg = get_args(arg)[0]
            logger.debug(f"{arg} marked as Lazy will not resolve yet")
            return LazyProxy(partial(self.resolve_arg, arg))

        args = list(get_args(arg)) or [arg]

        for req in args:
            if is_generic_type(req):
                try:
                    items.extend(self.resolve_arg(req))
                except RequirementNotFound:
                    pass
            else:
                items.extend(self.resolve(req, ))

        if len(items) == 0:
            if optional:
                raise OptionalRequirementNotFound("", arg, self)
            else:
                raise RequirementNotFound(f"Could not find {arg}", arg, self)
        if get_origin(arg) != list:
            if len(items) > 1:
                raise TooManyProviders(f"Too many {arg} found", items, self)
            else:
                return items[0]
        return items

    def is_supported(self, arg):
        try:
            return not issubclass(arg, str)
        except TypeError:
            return True

    def instantiation_chain(self):
        for node in walk(self, lambda s: s.parent):
            yield node


def print_context(context: InstantiationContext):
    stack = list(reversed(list(walk(context, lambda c: c.parent))))
    idx = 0
    print(f"{clsname(stack[0].compose)} Asked for: {clsname(stack[0].target)}")
    for current_context in stack:
        idx += 1
        indent = " " * idx
        print(f"{indent}Providing: {clsname(current_context.provider.provide_type)} ",
              f"via: {clsname(current_context.provider_bundle)}")
        source_definition = current_context.provider.provide_type
        for b in (current_context.provider.provide_type or object).__mro__:
            try:
                for f in fields(b):
                    if f.name == current_context.resolving_key:
                        source_definition = b
                        break
            except TypeError:
                continue
        print(f"{indent} +--{clsname(current_context.provider.provide_type)}.{current_context.resolving_key}",
              f"Requires: {clsname(current_context.resolving_type)}")
        print(f"{indent}      {clsname(current_context.provider.provide_type)}.{current_context.resolving_key} ",
              f"defined in {LocationInfo(source_definition)}")
