import typing
import fnmatch


def find(key: typing.Any, arr: typing.List[typing.Any]) -> int:
    for index, value in enumerate(arr):
        if (isinstance(value, list) or isinstance(value, tuple)) and key in value:
            return index
        elif value == key:
            return index
    return -1


def chunks(arr: list | tuple, n: int):
    """
    Yield n number of sequential chunks from list.
    From: https://stackoverflow.com/a/54802737/17106809
    """
    d, r = divmod(len(arr), n)
    for i in range(n):
        si = (d + 1) * (i if i < r else r) + d * (0 if i < r else i - r)
        yield arr[si:si + (d + 1 if i < r else d)]


def padding(arr: list | tuple, length: int, fill: typing.Any = None):
    """
    Pad the list to the specified length
    """
    return arr + ([fill] if isinstance(arr, list) else (fill,)) * (length - len(arr))


def getitem_pattern(data: dict, pattern: str) -> dict:
    """
    Get items from the dictionary that match the pattern
    """
    return {key: value for key, value in data.items() if fnmatch.fnmatch(key, pattern)}
