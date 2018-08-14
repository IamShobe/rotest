"""Define an abstract client."""
# pylint: disable=too-many-arguments
from itertools import count

from swaggapi.api.builder.client.requester import Requester

from rotest.api.common import ChangeResourcePostModel
from rotest.api.common.responses import BadRequestResponseModel
from rotest.api.resource_control import UpdateFields
from rotest.common import core_log
from rotest.common.config import (RESOURCE_MANAGER_PORT,
                                  RESOURCE_REQUEST_TIMEOUT)
from rotest.management.common.parsers import DEFAULT_PARSER
from rotest.management.common.resource_descriptor import ResourceDescriptor


class AbstractClient(object):
    """Abstract client class.

    Basic requests handling for communicating with the remote server.

    Attributes:
        logger (logging.Logger): resource manager logger.
        lock_timeout (number): default waiting time on requests.
        _host (str): server's host.
        _port (number): server's port.
        _messages_counter (itertools.count): msg_id counter.
    """
    BASE_URI = "rotest/api/"
    REPLY_OVERHEAD_TIME = 2
    _DEFAULT_REPLY_TIMEOUT = 18

    def __init__(self, host, port=RESOURCE_MANAGER_PORT,
                 base_uri=BASE_URI,
                 parser=DEFAULT_PARSER(),
                 lock_timeout=RESOURCE_REQUEST_TIMEOUT,
                 logger=core_log):
        """Initialize a socket connection to the server.

        Args:
            host (str): Server's IP address.
            parser (AbstractParser): parser to parse the messages with.
            lock_timeout (number): default waiting time on requests.
            logger (logging.Logger): client's logger.
        """
        self._host = host
        self._port = port
        self.base_uri = base_uri
        self.logger = logger
        self._messages_counter = count()
        self.lock_timeout = lock_timeout
        self._is_connected = False
        self.requester = Requester(host=self._host,
                                   port=self._port,
                                   base_url=self.base_uri,
                                   logger=self.logger)

    def connect(self, timeout=_DEFAULT_REPLY_TIMEOUT):
        """Connect to manager server.

        Args:
            timeout (number): time to wait for a reply from the server.
        """
        self._is_connected = True

    def is_connected(self):
        """Check if the socket is connected or not.

        Returns:
            bool. True if the socket is connected, False otherwise.
        """
        return self._is_connected

    def disconnect(self):
        """Disconnect from manager server.

        Raises:
            RuntimeError: wasn't connected in the first place.
        """
        self._is_connected = False

    def __enter__(self):
        """Connect to manager server."""
        self.connect()
        return self

    def __exit__(self, *args, **kwargs):
        """Disconnect from manager server."""
        self.disconnect()

    def update_fields(self, model, filter_dict=None, **kwargs):
        """Update content in the server's DB.

        Args:
            model (type): Django model to apply changes on.
            filter_dict (dict): arguments to filter by.
            kwargs (dict): the additional arguments are the changes to apply on
                the filtered instances.
        """
        if filter_dict is None:
            filter_dict = {}

        desc = ResourceDescriptor(resource_type=model, **filter_dict)

        request_data = ChangeResourcePostModel({
            "resource_descriptor": desc.encode(),
            "changes": kwargs
        })
        response = self.requester.request(UpdateFields,
                                          data=request_data,
                                          method="post")

        if isinstance(response, BadRequestResponseModel):
            raise Exception(response.details)
