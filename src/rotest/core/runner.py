"""Describes Rotest's test running handler class."""
# pylint: disable=too-many-arguments,too-many-locals,redefined-builtin
import os
import sys
import inspect
from collections import defaultdict

import click
import django

from rotest.common import core_log
from rotest.core.utils.json_parser import parse
from rotest.core.utils.common import print_test_hierarchy
from rotest.core.runners.base_runner import BaseTestRunner
from rotest.cli.discover import discover_tests_under_paths
from rotest.core.result.handlers.tags_handler import TagsHandler
from rotest.core.result.result import get_result_handler_options
from rotest.core import TestCase, TestFlow, TestBlock, TestSuite
from rotest.core.runners.multiprocess.manager.runner import MultiprocessRunner

LAST_RUN_INDEX = -1
MINIMUM_TIMES_TO_RUN = 1
FILE_FOLDER = os.path.dirname(__file__)
DEFAULT_SCHEMA_PATH = os.path.join(FILE_FOLDER, "schema.json")
DEFAULT_CONFIG_PATH = os.path.join(FILE_FOLDER, "default_config.json")


def get_runner(save_state=False, outputs=None, config=None,
               processes_number=None, run_delta=False, run_name=None,
               fail_fast=False, enable_debug=False, skip_init=None,
               stream=sys.stderr):
    """Return a test runner instance.

    Args:
        save_state (bool): determine if storing resources state is required.
            The behavior can be overridden using resource's save_state flag.
        outputs (list): list of the required output handlers' names.
        config (object): config object, will be transfered to each test.
        run_delta (bool): determine whether to run only tests that failed the
            last run (according to the results DB).
        processes_number (number): number of multiprocess runner's worker
            processes, None means that a regular runner will be used.
        run_name (str): name of the current run.
        fail_fast (bool): whether to stop the run on the first failure.
        enable_debug (bool): whether to enable entering ipdb debugging mode
            upon any exception in a test statement.
        skip_init (bool): True to skip resources initialize and validation.
        stream (file): output stream.

    Returns:
        runner. test runner instance.
    """
    if processes_number is not None and processes_number > 0:
        if enable_debug:
            raise RuntimeError("Cannot debug in multiprocess")

        return MultiprocessRunner(stream=stream,
                                  config=config,
                                  outputs=outputs,
                                  run_name=run_name,
                                  failfast=fail_fast,
                                  enable_debug=False,
                                  skip_init=skip_init,
                                  run_delta=run_delta,
                                  save_state=save_state,
                                  workers_number=processes_number)

    return BaseTestRunner(stream=stream,
                          config=config,
                          outputs=outputs,
                          run_name=run_name,
                          failfast=fail_fast,
                          run_delta=run_delta,
                          skip_init=skip_init,
                          save_state=save_state,
                          enable_debug=enable_debug)


def run(test_class, save_state=None, outputs=None, config=None,
        processes_number=None, delta_iterations=None, run_name=None,
        fail_fast=None, enable_debug=None, skip_init=None):
    """Return a test runner instance.

    Args:
        test_class (type): test class inheriting from
            :class:`rotest.core.case.TestCase` or
            :class:`rotest.core.suite.TestSuite` or
            :class:`rotest.core.flow.TestFlow` or
            :class:`rotest.core.block.TestBlock`.
        save_state (bool): determine if storing resources state is required.
            The behavior can be overridden using resource's save_state flag.
        outputs (list): list of the required output handlers' names.
        config (object): config object, will be transfered to each test.
        processes_number (number): number of multiprocess runner's worker
            processes, None means that a regular runner will be used.
        delta_iterations (number): determine whether to run only tests that
            failed the last run (according to the results DB), and how many
            times to do so. If delta_iterations = 0, the tests will run
            normally. If delta_iterations = 1, the 'delta-tests' will be run
            once. If delta_iterations > 1, the 'delta-tests' will run
            delta_iterations times.
        run_name (str): name of the current run.
        fail_fast (bool): whether to stop the run on the first failure.
        enable_debug (bool): whether to enable entering ipdb debugging mode
            upon any exception in a test statement.
        skip_init (bool): True to skip resources initialization and validation.

    Returns:
        list. list of RunData of the test runs.
    """
    times_to_run = max(delta_iterations, MINIMUM_TIMES_TO_RUN)

    runs_data = []
    test_runner = get_runner(config=config,
                             outputs=outputs,
                             run_name=run_name,
                             fail_fast=fail_fast,
                             skip_init=skip_init,
                             save_state=save_state,
                             enable_debug=enable_debug,
                             run_delta=bool(delta_iterations),
                             processes_number=processes_number)

    for _ in xrange(times_to_run):
        runs_data.append(test_runner.run(test_class))

    return runs_data


def parse_config_file(json_path, schema_path=DEFAULT_SCHEMA_PATH):
    """Parse configuration file to create the config dictionary.

    Args:
        json_path (str): path to the json config file.
        schema_path (str): path of the schema file - optional.

    Returns:
        AttrDict. configuration dict, containing default values for run
            options and other parameters.
    """
    if not os.path.exists(json_path):
        raise ValueError("Illegal config-path: %r" % json_path)

    core_log.debug('Parsing configuration file %r', json_path)
    config = parse(json_path=json_path,
                   schema_path=schema_path)

    return config


# Syntax symbol used to access the fields of Django models in querying
SUBFIELD_ACCESSOR = '__'


def parse_resource_identifiers(resources_str):
    """Update the tests' resources to ask for specific instances.

    Note:
        Requests which don't specify an instance will be handled automatically.

    Args:
        resources_str (str): string representation of the required resources.

    Example:
        input:
            'resource_a=demo_res1,resource_b.ip_address=10.0.0.1'
        output:
            {'resource_a': {'name': 'demo_res1'},
             'resource_b': {'ip_address': '10.0.0.1'}}

    Returns:
        dict. the parsed resource identifiers.
    """
    if resources_str is None or len(resources_str) == 0:
        return {}

    resource_requests = resources_str.split(',')

    requests_dict = defaultdict(dict)
    requests = (request.split('=', 1) for request in resource_requests)

    for resource_type, request_value in requests:
        request_fields = resource_type.split('.')
        if len(request_fields) == 1:
            requests_dict[resource_type]['name'] = request_value

        else:
            resource_name = request_fields[0]
            request_fields = request_fields[1:]
            resource_request = requests_dict[resource_name]
            resource_request[SUBFIELD_ACCESSOR.join(request_fields)] = \
                request_value

    return requests_dict


def _update_test_resources(test_element, identifiers_dict):
    """Update resource requests for a specific test.

    Args:
        test_element (type): target test class inheriting from
            :class:`rotest.core.case.TestCase or
            :class:`rotest.core.Suite.TestSuite or
            :class:`rotest.core.flow.TestFlow` or
            :class:`rotest.core.block.TestBlock`.
        identifiers_dict (dict): states the resources constraints in the
            form of <request name>: <resource constraints>.
    """
    requests_found = set()

    for resource_request in test_element.resources:
        if resource_request.name in identifiers_dict:
            resource_request.kwargs.update(
                identifiers_dict[resource_request.name])
            requests_found.add(resource_request.name)

    return requests_found


def update_requests(test_element, identifiers_dict):
    """Recursively update resources requests.

    Update requests to use specific resources according to the identifiers.

    Args:
        test_element (type): target test class inheriting from
            :class:`rotest.core.case.TestCase or
            :class:`rotest.core.Suite.TestSuite or
            :class:`rotest.core.flow.TestFlow` or
            :class:`rotest.core.block.TestBlock`.
        identifiers_dict (dict): states the resources constraints in the
            form of <request name>: <resource constraints>.

        Returns:
            set. the 'specific' constraints that were found and fulfilled.
    """
    requests_found = set()

    if issubclass(test_element, TestSuite):
        for component in test_element.components:
            requests_found.update(
                update_requests(component, identifiers_dict))

    if issubclass(test_element, (TestCase, TestFlow, TestBlock)):
        requests_found.update(
            _update_test_resources(test_element, identifiers_dict))

    return requests_found


def update_resource_requests(test_class, resource_identifiers):
    """Update the resources requests according to the parameters.

    Args:
        test_class (type): test class to update its resources, inheriting form
            :class:`rotest.core.case.TestCase or
            :class:`rotest.core.Suite.TestSuite or
            :class:`rotest.core.flow.TestFlow` or
            :class:`rotest.core.block.TestBlock`.
        resource_identifiers (dict): states the resources constraints in the
            form of <request name>: <resource constraints>.
    """
    specifics_fulfilled = update_requests(test_class, resource_identifiers)

    if len(specifics_fulfilled) != len(resource_identifiers):
        unfound_requests = list(set(resource_identifiers.keys()) -
                                specifics_fulfilled)
        raise ValueError("Tests do not contain requests of the names %s" %
                         unfound_requests)


def _output_option_parser(context, _parameter, value):
    """Parse the given CLI options for output handler.

    Args:
        context (click.Context): click context object.
        _parameter: unused click parameter name.
        value (str): given value in the CLI.

    Returns:
        list: requested output handler names.

    Raises:
        click.BadOptionUsage: if the user asked for non-existing handlers.
    """
    # CLI is more prioritized than what config file has set
    if value is not None:
        requested_handlers = set(value.split(","))
    else:
        requested_handlers = set(context.params["outputs"])

    available_handlers = set(get_result_handler_options())

    non_existing_handlers = requested_handlers - available_handlers

    if non_existing_handlers:
        raise click.BadOptionUsage(
            "The following output handlers are not existing: {}.\n"
            "Available options: {}.".format(
                ", ".join(non_existing_handlers),
                ", ".join(available_handlers)))

    return list(requested_handlers)


def _set_options_by_config(context, _parameter, config_path):
    """Set default CLI outputs based on the given configuration file.

    Args:
        context (click.Context): click context object.
        _parameter: unused click parameter name.
        config_path (str): given config file by the CLI.

    Returns:
        attrdict.AttrDict: configuration in a dict like object.
    """
    config = parse_config_file(config_path)

    for key, value in config.items():
        context.params[key] = value

    return config_path


def run_tests(paths, save_state, delta_iterations, processes, outputs, filter,
              run_name, list, fail_fast, debug, skip_init, config_path,
              resources):
    click.secho("Using config file at {}".format(os.path.relpath(config_path)))

    tests = discover_tests_under_paths(paths)

    if len(tests) == 0:
        click.secho("Found no tests at the given paths", bold=True)
        sys.exit(1)

    class AlmightySuite(TestSuite):
        components = tests

    if list:
        print_test_hierarchy(AlmightySuite, filter)
        return

    resource_identifiers = parse_resource_identifiers(resources)
    update_resource_requests(AlmightySuite, resource_identifiers)

    if filter:
        # Add a tags filtering handler.
        TagsHandler.TAGS_PATTERN = filter
        outputs.append('tags')

    runs_data = run(config=config_path,
                    test_class=AlmightySuite,
                    outputs=outputs,
                    run_name=run_name,
                    enable_debug=debug,
                    fail_fast=fail_fast,
                    skip_init=skip_init,
                    save_state=save_state,
                    processes_number=processes,
                    delta_iterations=delta_iterations)

    sys.exit(runs_data[-1].get_return_value())


@click.command(
    help="Run tests in a module or directory.",
    context_settings=dict(
        help_option_names=['-h', '--help'],
    )
)
@click.argument("paths",
                type=click.Path(exists=True),
                nargs=-1)
@click.option("config_path",
              "--config-path", "--config", "-c",
              is_eager=True,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True),
              callback=_set_options_by_config,
              help="Test configuration file path.")
@click.option("--save-state", "-s",
              is_flag=True,
              help="Enable saving state of resources.")
@click.option("delta_iterations",
              "--delta-iterations", "--delta", "-d",
              type=int,
              help="Enable run of failed tests only, enter the "
                   "number of times the failed tests should be run.")
@click.option("--processes", "-p",
              type=int,
              help="Use multiprocess test runner. "
                   "Specify number of worker processes to be created.")
@click.option("--outputs", "-o",
              callback=_output_option_parser,
              help="Output handlers separated by comma. Options: {}."
              .format(", ".join(get_result_handler_options())))
@click.option("--filter", "-f",
              help="Run only tests that match the filter expression, "
                   "e.g 'Tag1* and not Tag13'.")
@click.option("run_name",
              "--name", "-n",
              help="Assign a name for the current run.")
@click.option("--list", "-l",
              is_flag=True,
              help="Print the tests hierarchy and quit.")
@click.option("fail_fast",
              "--failfast", "-F",
              is_flag=True,
              help="Stop the run on first failure.")
@click.option("--debug", "-D",
              is_flag=True,
              help="Enter ipdb debug mode upon any test exception.")
@click.option("--skip-init", "-S",
              is_flag=True,
              help="Skip initialization & validation of resources.")
@click.option("--resources", "-r",
              help="Specify resources to request by attributes, e.g.: "
                   "'-r res1.group=QA,res2.comment=CI'.")
def main(paths, **kwargs):
    django.setup()

    if "rotest run" not in click.get_current_context().command_path:
        # If this function is called from within a file, find tests in it
        paths = [inspect.getfile(__import__("__main__"))]

    else:
        # The user ran "rotest run"
        paths = paths or ["."]

    run_tests(paths, **kwargs)
