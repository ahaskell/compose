import inspect
from contextlib import contextmanager
from dataclasses import fields
from itertools import chain
from typing import TypeVar, Type


from .bundling import ComposeBundle, FactoryBundle, bundle_key
from .context import InstantiationContext
from .exceptions import TooManyProviders, RequirementNotFound
from .extras import LocationInfo, clsname
from .extras.generics import *
from .extras.undef import Undefined
from .util import walk
from .modifiers import Required, Lazy



__all__ = [
    'Compose',
    'Required',
    'Lazy'
]




class Compose(object):

    @contextmanager
    def registry(self, bundle=None):
        """ Provide a context to make configuring Compose easier. Bind will
         automatically add the binding to the Bundle passed into the context.
        :return:
        """
        if bundle is not None:
            self.register(bundle)
        else:
            bundle = self._base_bundle
        stack = inspect.stack()
        stack[2].frame.f_locals[bundle_key] = bundle
        yield bundle
        del stack[2].frame.f_locals[bundle_key]

    def register(self, bundle):

        if isinstance(bundle, type):
            bundle = bundle()
        try:
            self._bundles.insert(0, bundle)
        except AttributeError:
            # When Compose is subclassed with a @dataclass decorated Class init is not called so we'll
            # give it a call.
            Compose.__init__(self,bundle)

    def __init__(self, *bundles: ComposeBundle):
        self._cached_instances = {}
        self._bundles = list(bundles)
        self._base_bundle = (self._bundles or [FactoryBundle()]).pop(0)

    i_T = TypeVar("i_T")

    def provide(self, kls: Type[i_T]) -> i_T:
        context = InstantiationContext(target=kls, parent=Undefined, compose=self)
        instances = list(self.provide_all(kls, context))
        if len(instances) > 1:
            raise TooManyProviders(f"{clsname(self)} found multiple bindings for {kls}", instances, context,
                                   location=self._bundles)
        elif len(instances) == 0:
            raise RequirementNotFound(f"{clsname(self)} could not find binding for {clsname(kls)}", kls, context,
                                      location=list(self._bundles + [self._base_bundle]))
        else:
            return instances[0]

    def provide_all(self, kls, context: InstantiationContext = Undefined):

        # instance = self._cached_instances.locate(kls)
        # if instance:
        # return instance
        if context is Undefined:
            context = InstantiationContext(target=kls, parent=context, compose=self)
        provided = False
        context.provider = None
        for bundle in chain(self._bundles, [self._base_bundle]):
            for provider in bundle.find(kls, context=context):
                context.provider = provider
                context.provider_bundle = bundle
                provided = True
                yield context.instance
            if provided:
                break
