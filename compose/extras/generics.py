import logging
import sys
import typing
from collections.abc import Callable as abcCallable

P38 = sys.version_info[:3] >= (3, 8, 0)
P37 = sys.version_info[:2] == (3, 7)

if not P38:
    logging.getLogger("compose.generics").warning("Version before 3.8 detected generics may not behave well")

__all__ = [
    'get_parameters',
    'get_origin',
    'get_args',
    'get_generic_bases',
    'get_bound',
    'get_constraints',

    'is_generic_type',
    'is_optional',
    'is_typevar',

    'resolve_type',

]


def get_parameters(tp):
    """Return type parameters of a parameterized type as a tuple.
    """
    try:
        return tp.__parameters__ if tp.__parameters__ is not None else ()
    except:
        return ()


try:
    get_origin = typing.get_origin
except:
    def get_origin(tp):
        """Get the unsubscripted version of a type. Supports generic types, Union,
        Callable, and Tuple. Returns None for unsupported types. Examples::
        """
        if isinstance(tp, typing._GenericAlias):
            return tp.__origin__ if tp.__origin__ is not typing.ClassVar else None
        if tp is typing.Generic:
            return typing.Generic
        return None

try:
    get_args = typing.get_args
except:
    def get_args(tp, evaluate=None):
        """Get type arguments with all substitutions performed. For unions,
        basic simplifications used by Union constructor are performed.
        On versions prior to 3.7 if `evaluate` is False (default),
        report result as nested tuple, this matches
        the internal representation of types. If `evaluate` is True
        (or if Python version is 3.7 or greater), then all
        type parameters are applied (this could be time and memory expensive).
        Examples::


        """
        if evaluate is not None and not evaluate:
            raise ValueError('evaluate can only be True in Python 3.7')
        if isinstance(tp, typing._GenericAlias):
            res = tp.__args__
            if get_origin(tp) is abcCallable and res[0] is not Ellipsis:
                res = (list(res[:-1]), res[-1])
            return res
        return ()


def get_generic_bases(tp):
    """Get generic base types of a type or empty tuple if not possible.
    """
    org = getattr(tp, '__origin__', None)
    if org:
        a = (org,)
    else:
        a = ()
    return a + getattr(tp, "__orig_bases__", ())


def is_generic_type(kls):
    """Test if the given type is a generic type. This includes Generic itself, but
    excludes special typing constructs such as Union, Tuple, Callable, ClassVar.
    See Unit tests for examples and expected outcomes.
    """
    if isinstance(kls, typing._GenericAlias):
        if isinstance(kls.__origin__, typing._SpecialForm) or kls.__origin__ == abcCallable:
            return False
        return True
    # noinspection PyTypeHints
    return isinstance(kls, type) and issubclass(kls, typing.Generic)


def resolve_type(cls, type_name, parent=None):
    if isinstance(type_name, str) and type_name[0] != "~":
        type_name = "~" + type_name
    for base in get_generic_bases(cls):
        res = resolve_type(base, type_name, parent=cls)
        if res is not None and str(res) != str(type_name):
            return res

    for idx, parm in enumerate(get_parameters(cls)):
        if str(parm) == str(type_name):
            try:
                return get_args(parent)[idx]
            except IndexError:
                pass
    return None


def is_optional(kls):
    """Returns `True` if the type is `type(None)`, has a Union to none, like Optional[],  Nested `Union` arguments
     are inspected

     `TypeVar` Edge case:
        TypeVar` definitions are not inspected. If only the bound/constraint of a typevar is Optional is_optional
        will return False. (see edge case test for clarity)
    """

    if kls is type(None):
        return True
    return any(is_optional(sub_kls) for sub_kls in get_args(kls))


# Simple accessors instead of accessing __ attributes, they tend to change a bt right now.

def get_bound(kls):
    """Returns the type bound to a `TypeVar` if any. Fails if not TypeVar
    """
    assert_typevar(kls)
    return getattr(kls, '__bound__', None)


def get_constraints(kls):
    """Returns the constraints of a `TypeVar` if any. Fails if not TypeVar"""

    assert_typevar(kls)
    return getattr(kls, '__constraints__', ())


def assert_typevar(kls):
    """A more forceful check for typevar. If the type is not a `TypeVar`, a `TypeError` is raised"""
    if is_typevar(kls):
        return
    raise TypeError(f"'{kls.__name__}' is not a `TypeVar`")


def is_typevar(tp):
    """Test if the type represents a type variable. Examples::
    """

    return type(tp) is typing.TypeVar
