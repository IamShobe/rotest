=============================
Adding Custom Output Handlers
=============================

Third Party Output Handlers
===========================

* `rotest_reportportal <https://github.com/gregoil/rotest_reportportal>`_

  - Plugin to the amazing `Report Portal <http://reportportal.io/>`_ system,
    that enables viewing test results and investigating them.

How to Make Your Own Output Handler
===================================

You can make your own Output Handler, following the next two steps:

* Inheriting from
  :class:`rotest.core.result.handlers.abstract_handler.AbstractResultHandler`,
  and overriding the relevant methods.

* Register the above inheriting class as an entrypoint, in a setup.py file, and
  make sure it's being install on the environment.

For an example, please refer to
`rotest_reportportal <https://github.com/gregoil/rotest_reportportal>`_ plugin.

Available Events
================

The available methods of an output handler:

.. autoclass:: rotest.core.result.handlers.abstract_handler.AbstractResultHandler
    :members:
