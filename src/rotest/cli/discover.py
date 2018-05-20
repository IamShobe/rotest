# pylint: disable=protected-access
import os
import sys
import unittest
from fnmatch import fnmatch

from isort.pie_slice import OrderedSet

from rotest.core import TestCase, TestFlow


BLACK_LIST = [".tox", ".git", ".idea", "setup.py"]
WHITE_LIST = ["*test*.py"]


def is_test_class(test):
    """Return if the provided object is a runnable test.

    Args:
        test (object): the object to be inspected.

    Returns:
        bool: whether it's either TestCase or TestFlow, and should be ran.
    """
    return (isinstance(test, type) and
            issubclass(test, (TestCase, TestFlow)) and
            test not in (TestFlow, TestCase) and
            getattr(test, "__test__", True))


def guess_root_dir(path):
    """Get the first upward directory not containing an __init__.py.

    Returns:
        str: the first upward directory which is not a package.
    """
    path = os.path.dirname(path)
    while os.path.exists(os.path.join(path, "__init__.py")):
        path = os.path.dirname(path)

    return path


def get_test_files(paths):
    """Return test files that match whitelist and blacklist patterns.

    Args:
        paths (iterable): list of filesystem paths to be looked recursively.

    Yields:
        str: path of test file.
    """
    for path in paths:
        path = os.path.abspath(path)
        filename = os.path.basename(path)

        if any(fnmatch(filename, pattern) for pattern in BLACK_LIST):
            continue

        if os.path.isfile(path):
            if not any(fnmatch(filename, pattern) for pattern in WHITE_LIST):
                continue

            yield path

        else:
            sub_files = (os.path.join(path, filename)
                         for filename in os.listdir(path))

            for sub_file in get_test_files(sub_files):
                yield sub_file


def discover_tests_under_paths(paths):
    """Search recursively for every test class under the given paths.

    Args:
        paths (iterable): list of filesystem paths to be searched.

    Returns:
        set: all discovered tests.
    """
    loader = unittest.TestLoader()

    loader.suiteClass = list
    loader.loadTestsFromTestCase = lambda test: test

    tests = OrderedSet()

    for path in get_test_files(paths):
        top_level_dir = guess_root_dir(path)
        loader._top_level_dir = top_level_dir
        sys.path.insert(0, top_level_dir)

        module_name = loader._get_name_from_path(path)

        tests_discovered = loader.loadTestsFromName(module_name)
        tests_discovered = [test
                            for test in tests_discovered
                            if is_test_class(test)]

        tests.update(tests_discovered)

    return tests
