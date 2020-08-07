import inspect
import sys
from contextlib import contextmanager
from importlib._bootstrap import ModuleSpec
from pkgutil import ModuleInfo, walk_packages
from typing import Generator, List, Text, cast

from ._key import bundle_key
from .binding import Binding, Bind
from ..extras import Undefined, is_generic_type, get_origin, get_parameters, resolve_type, get_bound, clsname
from ..extras.logging import logger
from ..util import is_resolvable


class ComposeBundle(object):
    def __init__(self):
        self._bundles = []
        self._context_factories()

    def _context_factories(self):
        for k, v in inspect.getmembers(self.__class__, lambda a: isinstance(a, FactoryBundle)):
            delattr(self.__class__, k)
            self.extend(v)

    def extend(self, bundle):
        self._bundles.append(bundle)

    def search(self, kls, context: 'InstantiationContext') -> Generator['Binding', None, None]:
        raise NotImplementedError("Bundles at a minimum must support find")

    def find(self, kls, context) -> Generator['Binding', None, None]:
        yield from self.search(kls, context)
        # This could be dangerous if bundles have circular references probably need to add some logic to prevent
        for ext in self._bundles:
            yield from ext.find(kls, context)

    def visit(self, config: 'ComposeConfig'):
        config.accept(self)

    def add_binding(self, biniding):
        raise NotImplementedError()

    @contextmanager
    def registry(self):
        """ Provide a context to make configuring Compose easier. Bind will
         automatically add the binding to the Bundle passed into the context.
        :return:
        """

        stack = inspect.stack()
        stack[2].frame.f_locals[bundle_key] = self
        yield self
        del stack[2].frame.f_locals[bundle_key]


class FactoryBundle(ComposeBundle):
    def __init__(self):
        super().__init__()
        self._factories: List[Binding] = []

    def add_binding(self, bind: Bind = Undefined):
        self._factories.insert(0, bind)

    def remove_binding(self, bind: Bind = Undefined):
        try:
            idx = self._factories.index(bind)
        except ValueError:
            return None
        return self._factories.pop(idx)

    def search(self, kls, context):
        resolve_templates = None
        if is_generic_type(kls) and get_origin(kls) is not type:
            resolve_templates = get_parameters(get_origin(kls))
            resolve_templates = list((t, resolve_type(kls, t) or get_bound(t)) for t in resolve_templates)
            kls = get_origin(kls)

        for factory in self._factories:
            try:
                if factory.provides(kls, templates=resolve_templates, context=context):
                    yield factory
            except TypeError as ex:
                # We could check in the search for is_resolvable but since a FactoryBundle could
                # implement something to make an item Compose thinks is unresolvable resolvable we ask the
                # factories and just hide any errors if compose thinks it is unresolvable
                if is_resolvable(kls):
                    logger.error("Factory can not respond to it's ability to provide {kls}. Error follows, "
                                 "but compose Moving on to the next factory.")
                    logger.exception(ex)
                else:
                    logger.debug(f"Factory choked on unresolvable type '{kls}', generally this is ignorable "
                                 f"since {kls} is considered unresolvable. Here was the error: {ex}")


class AutoBundle(FactoryBundle):
    @staticmethod
    def _find_main():
        for frame_info in inspect.stack():
            try:
                if frame_info.frame.f_locals["__name__"] == "__main__":
                    return frame_info
            except KeyError:
                pass
        return None

    def __init__(self, paths=None, add_main=False):
        super().__init__()
        if paths:
            self.discover(paths)
        if add_main:
            self._add_main()

    def _add_main(self):
        main = self._find_main()
        for kls in self.filter_classes(main.frame.f_locals.items(), "__main__"):
            self.add_binding(Bind(kls).add(kls))

    def discover(self, spec, package_name: Text = None):
        modules = []
        if hasattr(spec, "__spec__"):
            spec = spec.__spec__

        if isinstance(spec, ModuleSpec):
            modules = self.crawl(spec)

        for module in modules:
            if module is None:
                continue
            self.inspect_module(module)

    def crawl(self, spec: ModuleSpec):
        try:
            package_path = spec.submodule_search_locations
        except AttributeError:
            spec = cast(ModuleInfo, spec)
            package_path = [spec.module_finder.path]
        package_name = spec.name
        for m in walk_packages(package_path, package_name + ".", onerror=lambda e: ""):
            yield self.module_info_to_module(m)

    def module_info_to_module(self, m):
        name = m.name
        if m.name in sys.modules:
            module = sys.modules[m.name]
        else:
            loader = m.module_finder.find_loader(name)
            try:
                module = loader[0].load_module(name)
            except Exception as ex:
                logger.debug(f"Import error....skipping {name}", exc_info=ex)
                return
        return module

    def inspect_module(self, module):
        name = module.__name__
        if name == "context.py":
            return
        for n, member in inspect.getmembers(module):
            if n in ("job_context", "logger", "logging", "os", "sys"):
                continue
            if inspect.ismodule(member):
                self.inspect_module(member)
                continue
            if isinstance(member, type):
                if member.__module__ == name:
                    if not getattr(member, f"_{clsname(member)}_compose_abstract", False):
                        self.add_binding(Binding(member).to_self())
