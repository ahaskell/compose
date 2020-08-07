import inspect
import weakref
from functools import partial
from typing import Callable, Generic, TypeVar

from ._key import bundle_key
from ..exceptions import RequirementNotFound, AmbiguousDependency
from ..extras import clsname
from ..extras.generics import is_generic_type, get_origin, resolve_type
from ..extras.logging import logger
from ..extras.undef import Undefined, default


class _RebindContext(object):
    def __init__(self, bundle):
        self._bundle = bundle

    @property
    def parent(self):
        return Undefined

    def __getattr__(self, item):
        return object.__getattribute__(self, "_bundle").__getattribute__(item)


class BindMeta(type):

    def __getitem__(cls, item) -> 'Binding':
        c_local = cls.caller_local()
        bundle = c_local.get(bundle_key, Undefined)
        if bundle is Undefined:
            from compose import FactoryBundle
            c_local[bundle_key] = FactoryBundle()
            bundle = c_local[bundle_key]
        binding = None
        if cls == ReBind:
            binding = list(bundle.find(item, _RebindContext(bundle)))
            if len(binding):
                binding = binding[0]
            else:
                binding = None
                logger.warning("Rebind could not find previous binding. Binding instead")

        if binding is None:
            binding = Binding(item)
            bundle.visit(binding)

        return binding

    def caller_local(cls):
        stack = inspect.stack()
        for frame_info in stack:
            if frame_info.frame.f_locals.get("cls", None) != cls:
                return frame_info.frame.f_locals
        return {}


class Bind(object, metaclass=BindMeta):
    """Binding creates a whole new binding This is generally what should be used  we setting up a configuration
    with Compose

    """
    pass


class ReBind(object, metaclass=BindMeta):
    """Rebind will attempt to find previously configured bindings and update the factory.

     This can be useful in scenarios where a higher level framework wants to configure scopingbut allow
     the lower level application to define the binding itself. It can also be used to allow for a default binding
     to be overridden later but the more acceptable way to do that is to have mmultiple bundles since bundles cascade
     only when a bundle does not provide and instance.

    """
    pass


T = TypeVar("T", bound=type)


class Binding(Generic[T]):

    def __init__(self, bind: T):
        self.is_singleton = False
        self._as_singleton = False
        self._config_for = bind
        self._factory = None
        self._additional_check = lambda *a: True
        self.provide_type = None

    def to_multiple(self, *factories):
        for factory in factories:
            self._bundle.add_binding(Binding(self._config_for).to(factory))
        self._bundle.remove_binding(self)
        self._bundle = None
        return None

    def to(self, factory: Callable):
        if isinstance(factory, list):
            raise ValueError("Each factory binding must be its own binding, use to_multiple for an easier syntax")
        if not callable(factory) and not isinstance(factory, str):
            raise RuntimeError("NOT CALLABLE!!!")
        self._factory = factory
        if isinstance(factory, (type, str)):
            self.provide_type = factory
        else:
            self.provide_type = inspect.signature(factory).return_annotation
        if self.provide_type is inspect.Signature.empty:
            self.provide_type = Undefined
            msg = f"Provided factory does not specify a return type in the annotation, some providers rely on this" \
                  f" to detirmine if they provide a class or not. "
            logger.warning(msg)
        return self

    def on_target(self, target):
        def check(kls, context: 'InstantiationContext'):
            for node in list(context.instantiation_chain()):
                if node.provider.provide_type == target:
                    return True
            return False

        return check

    def on(self, predicate) -> 'Binding':
        self._additional_check = predicate
        if isinstance(predicate, type):
            self._additional_check = self.on_target(predicate)
        return self

    def to_self(self) -> 'Binding':
        return self.to(self._config_for)

    def as_singleton(self):
        self._as_singleton = True
        return self

    def accept(self, bundle: 'ComposeBundle'):
        self._bundle = weakref.proxy(bundle)
        bundle.add_binding(self)

    def with_args(self, *args, **kwargs):
        self._factory = partial(self._factory, *args, **kwargs)
        return self

    @property
    def factory(self):
        if isinstance(self._factory, str):
            for sub in self._config_for.__subclasses__():
                if clsname(sub, full=True) == self._factory:
                    return sub
            raise RequirementNotFound(f"No Subclass discovered by name {self._factory}", self._factory, Undefined)
        else:
            return self._factory

    def provides(self, kls, templates=None, context=Undefined):
        provides = False
        if is_generic_type(kls) and get_origin(kls) is type:
            if self._config_for == kls:
                provides = True
        if not provides:
            try:
                if isinstance(kls, type) and issubclass(kls, self._config_for):
                    if not templates or all(issubclass(ot, resolve_type(self._config_for, t)) for t, ot in templates):
                        provides = True
            except TypeError as ex:
                if isinstance(kls, TypeVar):
                    msg = f"A generic type was found and can not be resolved. This usually happens when a property on " \
                          f"a dataclass is typed with a generic class without specifying the types of the generics. For " \
                          f"example my_prop:Mapping = field(default=None). Compose can not resolve Mapping, mapping of what?"
                    raise AmbiguousDependency(msg, context)
                raise ex
        if provides:
            if isinstance(self.provide_type, str):
                self.provide_type = self.factory
            return self._additional_check(kls, default(context.parent, context))
        return False

    @property
    def bound_to(self):
        return self._config_for
