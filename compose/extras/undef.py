__all__ = [
    'Undefined',
    'is_defined',
    'default'

]


class UndefinedMeta(type):
    def __getitem__(self, item):
        return "-"

    def __len__(self):
        return 0


class Undefined(object, metaclass=UndefinedMeta):
    """ Useful when a default value can't be none b/c None has significant meaning in the code.

        `def myfunc(positional1, keyword=Undefined) `

    """


def default(item, default_value):
    if not callable(default_value):
        call_default = lambda: default_value
    else:
        call_default = default_value
    ret = item if is_defined(item) else call_default()
    return ret


def is_defined(item):
    """ Used in conjunction with Undefined. The main purpose of this method is to make code more readable.
    otherwise the code is littered with double negatives since the most common use of Undefined is to set
    a default value in a function.

    foo = foo if is_defined(foo) else 'BAR'

    reads better than
    foo = foo if foo is not Undefined else 'BAR'

    :param item:
    :return:
    """
    return item is not Undefined
