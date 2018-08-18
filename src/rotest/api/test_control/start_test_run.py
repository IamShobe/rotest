import uuid
import httplib

from django.http import JsonResponse
from swaggapi.api.builder.server.request import DjangoRequestView

from rotest.core.models import RunData
from rotest.api.common.models import StartTestRunModel
from rotest.api.common.responses import TokenResponseModel
from rotest.management.common.json_parser import JSONParser
from rotest.api.test_control.session_data import SessionData
from rotest.api.test_control.middleware import session_middleware
# pylint: disable=unused-argument, no-self-use


TEST_ID_KEY = 'id'
TEST_NAME_KEY = 'name'
TEST_CLASS_CODE_KEY = 'class'
TEST_SUBTESTS_KEY = 'subtests'


class StartTestRun(DjangoRequestView):
    """Initialize the tests run data.

    Args:
        tests_tree (dict): contains the hierarchy of the tests in the run.
        run_data (dict): contains additional data about the run.
    """
    URI = "tests/start_test_run"
    DEFAULT_MODEL = StartTestRunModel
    DEFAULT_RESPONSES = {
        httplib.OK: TokenResponseModel,
    }
    TAGS = {
        "post": ["Tests"]
    }

    def _create_test_data(self, test_dict, run_data, all_tests):
        """Recursively create the test's datas and add them to 'all_tests'.

        Args:
            tests_tree (dict): contains the hierarchy of the tests in the run.

        Returns:
            GeneralData. the created test data object.
        """
        parser = JSONParser()
        data_type = parser.decode(test_dict[TEST_CLASS_CODE_KEY])
        test_data = data_type(name=test_dict[TEST_NAME_KEY])
        test_data.run_data = run_data
        test_data.save()
        all_tests[test_dict[TEST_ID_KEY]] = test_data

        if TEST_SUBTESTS_KEY in test_dict:
            for sub_test_dict in test_dict[TEST_SUBTESTS_KEY]:
                sub_test = self._create_test_data(sub_test_dict,
                                                  run_data,
                                                  all_tests)
                test_data.add_sub_test_data(sub_test)
                sub_test.save()

        return test_data

    @session_middleware
    def post(self, request, sessions, *args, **kwargs):
        """Initialize the tests run data.

        Args:
            tests_tree (dict): contains the hierarchy of the tests in the run.
            run_data (dict): contains additional data about the run.
        """
        run_data = RunData.objects.create(**request.model.run_data)
        all_tests = {}
        tests_tree = request.model.tests
        main_test = self._create_test_data(tests_tree, run_data, all_tests)
        run_data.main_test = main_test
        run_data.user_name = request.get_host()
        run_data.save()

        session_token = str(uuid.uuid4())
        sessions[session_token] = SessionData(all_tests=all_tests,
                                              run_data=run_data,
                                              main_test=main_test,
                                              user_name=run_data.user_name)
        response = {
            "token": session_token
        }
        return JsonResponse(response, status=httplib.OK)