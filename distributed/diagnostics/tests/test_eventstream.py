from __future__ import print_function, division, absolute_import

from copy import deepcopy
from time import sleep

import pytest
from tornado import gen

from distributed import Client, Scheduler, Worker
from distributed.core import read
from distributed.client import _wait
from distributed.diagnostics.eventstream import EventStream, eventstream
from distributed.diagnostics.progress_stream import task_stream_append
from distributed.metrics import time
from distributed.utils_test import inc, div, dec, gen_cluster
from distributed.worker import dumps_task


@gen_cluster(client=True, ncores=[('127.0.0.1', 1)] * 3)
def test_eventstream(c, s, *workers):
    es = EventStream()
    s.add_plugin(es)
    assert es.buffer == []

    futures = c.map(div, [1] * 10, range(10))
    total = c.submit(sum, futures[1:])
    yield _wait(total)

    assert len(es.buffer) == 11

    from distributed.bokeh import messages
    lists = deepcopy(messages['task-events']['rectangles'])
    workers = dict()
    for msg in es.buffer:
        task_stream_append(lists, msg, workers)

    assert len([n for n in lists['name'] if n.startswith('transfer')]) == 2
    for name, color in zip(lists['name'], lists['color']):
        if name == 'transfer':
            assert color == 'red'

    assert any(c == 'black' for c in lists['color'])


@gen_cluster(client=True)
def test_eventstream_remote(c, s, a, b):
    base_plugins = len(s.plugins)
    stream = yield eventstream(s.address, interval=0.010)

    start = time()
    while len(s.plugins) == base_plugins:
        yield gen.sleep(0.01)
        assert time() < start + 5

    futures = c.map(div, [1] * 10, range(10))

    start = time()
    total = []
    while len(total) < 10:
        msgs = yield read(stream)
        assert isinstance(msgs, list)
        total.extend(msgs)
        assert time() < start + 5

    stream.close()
    start = time()
    while len(s.plugins) > base_plugins:
        yield gen.sleep(0.01)
        assert time() < start + 5
