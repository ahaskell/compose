import inspect
from functools import wraps
from typing import TypeVar, Generic

__all__ = [
    'alias',
    'ignore',
    'Required',
    'Lazy'
]


def alias(target: property):
    """ this is a decorator that will allow a subclass to alias a property defined on its parent class.
    This can be useful if the subclass has a more specific return type and/or when the super class has a more
    generic name. Such is the case often when dealing with hierarchical classes.

    :param property target: the property to be aliased
    :return: property that has proper meta data for return type etc.
    """

    def decorator(f):
        prop_type = inspect.signature(f).return_annotation
        try:
            aliased_type = inspect.signature(target.fget).return_annotation
        except AttributeError:
            raise TypeError("Alias does not support non-property stuff. Make sure what is being passed is a @property")

        if isinstance(aliased_type, TypeVar):
            aliased_type = aliased_type.__bound__

        if not issubclass(prop_type, aliased_type):
            raise TypeError('Property must have a compatible type to the aliased property')

        @wraps(f)
        def getter(self):
            return getattr(self, target.fget.__name__)

        @wraps(f)
        def setter(self, arg: prop_type):
            setattr(self, target.fset.__name__, arg)

        @wraps(f)
        def deleter(self):
            delattr(self, target.fset.__name__)

        return property(getter, setter, deleter)

    return decorator


def ignore(kls):
    """During auto-discovery sometimes you don't want a base class

    :param kls:
    :return:
    """
    setattr(kls, f"_{kls.__name__}_compose_abstract", True)
    return kls


required_T = TypeVar("required_T")


class Required(Generic[required_T]):
    """Sometimes a field of a dataclass must of a default value but the desire is for Compose to require that
    field be made available during instantiation. This can be used as the default. for the field:

        bar = field(default=Required)
    Class made a generic for future compatibility with using Required like Optional
    """
    pass


l_T = TypeVar("l_T")


class Lazy(Generic[l_T]):
    pass
