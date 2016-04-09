# encoding=UTF8

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Unit tests for the DB API."""

import copy
import datetime
import uuid as stdlib_uuid

import iso8601
import mock
import netaddr
from oslo_config import cfg
from oslo_db import api as oslo_db_api
from oslo_db import exception as db_exc
from oslo_db.sqlalchemy import enginefacade
from oslo_db.sqlalchemy import test_base
from oslo_db.sqlalchemy import update_match
from oslo_db.sqlalchemy import utils as sqlalchemyutils
from oslo_serialization import jsonutils
from oslo_utils import fixture as utils_fixture
from oslo_utils import timeutils
from oslo_utils import uuidutils
import six
from six.moves import range
from sqlalchemy import Column
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
from sqlalchemy import Integer
from sqlalchemy import MetaData
# from sqlalchemy.orm import query
from lib.rome.core.orm.query import Query
from sqlalchemy import sql
from sqlalchemy import Table
import unittest

from nova import block_device
from nova.compute import arch
from nova.compute import task_states
from nova.compute import vm_states
#from nova import context
from nova import db
# from nova.db.sqlalchemy import api as sqlalchemy_api
# from nova.db.sqlalchemy import models
from nova.db.discovery import api as sqlalchemy_api
from nova.db.discovery import models
from nova.db.sqlalchemy import types as col_types
from nova.db.sqlalchemy import utils as db_utils
from nova import exception
from nova import objects
from nova.objects import fields
from nova import quota
from nova import test
from nova.tests.unit import matchers
from nova.tests import uuidsentinel
from nova import utils
from nova.db.discovery import context

CONF = cfg.CONF
CONF.import_opt('reserved_host_memory_mb', 'nova.compute.resource_tracker')
CONF.import_opt('reserved_host_disk_mb', 'nova.compute.resource_tracker')

get_engine = sqlalchemy_api.get_engine



import logging
logging.getLogger().setLevel(logging.DEBUG)

rome_ignored_keys = ["updated_at", "_rome_version_number", "_metadata_novabase_classname", "_session", "_nova_classname", "_rid"]
import re

def _get_fake_aggr_values():
    return {'name': 'fake_aggregate'}


def _get_fake_aggr_metadata():
    return {'fake_key1': 'fake_value1',
            'fake_key2': 'fake_value2',
            'availability_zone': 'fake_avail_zone'}


def _get_fake_aggr_hosts():
    return ['foo.openstack.org']


def _create_aggregate(context=context.get_admin_context(),
                      values=_get_fake_aggr_values(),
                      metadata=_get_fake_aggr_metadata()):
    return db.aggregate_create(context, values, metadata)


def _create_aggregate_with_hosts(context=context.get_admin_context(),
                      values=_get_fake_aggr_values(),
                      metadata=_get_fake_aggr_metadata(),
                      hosts=_get_fake_aggr_hosts()):
    result = _create_aggregate(context=context,
                               values=values, metadata=metadata)
    for host in hosts:
        db.aggregate_host_add(context, result['id'], host)
    return result

class AggregateDBApiTestCase(test.TestCase):
    def setUp(self):
        super(AggregateDBApiTestCase, self).setUp()
        self.user_id = 'fake'
        self.project_id = 'fake'

    def tearDown(self):
        "Hook method for deconstructing the test fixture after testing it."
        super(AggregateDBApiTestCase, self).tearDown()
        classes = [models.AggregateMetadata, models.Aggregate, models.AggregateHost]
        for c in classes:
            for o in Query(c).all():
                o.delete()
        pass

    # def test_aggregate_create_no_metadata(self):
    #     result = _create_aggregate(metadata=None)
    #     self.assertEqual(result['name'], 'fake_aggregate')
    #
    # def test_aggregate_create_avoid_name_conflict(self):
    #     r1 = _create_aggregate(metadata=None)
    #     db.aggregate_delete(context.get_admin_context(), r1['id'])
    #     values = {'name': r1['name']}
    #     metadata = {'availability_zone': 'new_zone'}
    #     r2 = _create_aggregate(values=values, metadata=metadata)
    #     self.assertEqual(r2['name'], values['name'])
    #     self.assertEqual(r2['availability_zone'],
    #             metadata['availability_zone'])
    #
    # def test_aggregate_create_raise_exist_exc(self):
    #     _create_aggregate(metadata=None)
    #     self.assertRaises(exception.AggregateNameExists,
    #                       _create_aggregate, metadata=None)
    #
    # def test_aggregate_get_raise_not_found(self):
    #     ctxt = context.get_admin_context()
    #     # this does not exist!
    #     aggregate_id = 1
    #     self.assertRaises(exception.AggregateNotFound,
    #                       db.aggregate_get,
    #                       ctxt, aggregate_id)
    #
    # def test_aggregate_metadata_get_raise_not_found(self):
    #     ctxt = context.get_admin_context()
    #     # this does not exist!
    #     aggregate_id = 1
    #     self.assertRaises(exception.AggregateNotFound,
    #                       db.aggregate_metadata_get,
    #                       ctxt, aggregate_id)
    #
    # def test_aggregate_create_with_metadata(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     expected_metadata = db.aggregate_metadata_get(ctxt, result['id'])
    #     assertThat(expected_metadata,
    #                     matchers.DictMatches(_get_fake_aggr_metadata()))
    #
    # def test_aggregate_create_delete_create_with_metadata(self):
    #     # test for bug 1052479
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     expected_metadata = db.aggregate_metadata_get(ctxt, result['id'])
    #     self.assertThat(expected_metadata,
    #                     matchers.DictMatches(_get_fake_aggr_metadata()))
    #     db.aggregate_delete(ctxt, result['id'])
    #     result = _create_aggregate(metadata={'availability_zone':
    #         'fake_avail_zone'})
    #     expected_metadata = db.aggregate_metadata_get(ctxt, result['id'])
    #     self.assertEqual(expected_metadata, {'availability_zone':
    #         'fake_avail_zone'})
    #
    # def test_aggregate_get(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate_with_hosts(context=ctxt)
    #     expected = db.aggregate_get(ctxt, result['id'])
    #     self.assertEqual(_get_fake_aggr_hosts(), expected['hosts'])
    #     self.assertEqual(_get_fake_aggr_metadata(), expected['metadetails'])

    def test_aggregate_get_by_host(self):
        ctxt = context.get_admin_context()
        values2 = {'name': 'fake_aggregate2'}
        values3 = {'name': 'fake_aggregate3'}
        values4 = {'name': 'fake_aggregate4'}
        values5 = {'name': 'fake_aggregate5'}
        a1 = _create_aggregate_with_hosts(context=ctxt)
        a2 = _create_aggregate_with_hosts(context=ctxt, values=values2)
        # a3 has no hosts and should not be in the results.
        _create_aggregate(context=ctxt, values=values3)
        # a4 has no matching hosts.
        _create_aggregate_with_hosts(context=ctxt, values=values4,
                hosts=['foo4.openstack.org'])
        # a5 has no matching hosts after deleting the only matching host.
        a5 = _create_aggregate_with_hosts(context=ctxt, values=values5,
                hosts=['foo5.openstack.org', 'foo.openstack.org'])
        db.aggregate_host_delete(ctxt, a5['id'],
                                 'foo.openstack.org')
        r1 = db.aggregate_get_by_host(ctxt, 'foo.openstack.org')
        self.assertEqual([a1['id'], a2['id']], [x['id'] for x in r1])

    def test_aggregate_get_by_host_with_key(self):
        ctxt = context.get_admin_context()
        values2 = {'name': 'fake_aggregate2'}
        values3 = {'name': 'fake_aggregate3'}
        values4 = {'name': 'fake_aggregate4'}
        a1 = _create_aggregate_with_hosts(context=ctxt,
                                          metadata={'goodkey': 'good'})
        _create_aggregate_with_hosts(context=ctxt, values=values2)
        _create_aggregate(context=ctxt, values=values3)
        _create_aggregate_with_hosts(context=ctxt, values=values4,
                hosts=['foo4.openstack.org'], metadata={'goodkey': 'bad'})
        # filter result by key
        r1 = db.aggregate_get_by_host(ctxt, 'foo.openstack.org', key='goodkey')
        self.assertEqual([a1['id']], [x['id'] for x in r1])

    def test_aggregate_metadata_get_by_host(self):
        ctxt = context.get_admin_context()
        values = {'name': 'fake_aggregate2'}
        values2 = {'name': 'fake_aggregate3'}
        _create_aggregate_with_hosts(context=ctxt)
        _create_aggregate_with_hosts(context=ctxt, values=values)
        _create_aggregate_with_hosts(context=ctxt, values=values2,
                hosts=['bar.openstack.org'], metadata={'badkey': 'bad'})
        r1 = db.aggregate_metadata_get_by_host(ctxt, 'foo.openstack.org')
        self.assertEqual(r1['fake_key1'], set(['fake_value1']))
        self.assertNotIn('badkey', r1)

    # def test_aggregate_metadata_get_by_host_with_key(self):
    #     ctxt = context.get_admin_context()
    #     values2 = {'name': 'fake_aggregate12'}
    #     values3 = {'name': 'fake_aggregate23'}
    #     a2_hosts = ['foo1.openstack.org', 'foo2.openstack.org']
    #     a2_metadata = {'good': 'value12', 'bad': 'badvalue12'}
    #     a3_hosts = ['foo2.openstack.org', 'foo3.openstack.org']
    #     a3_metadata = {'good': 'value23', 'bad': 'badvalue23'}
    #     _create_aggregate_with_hosts(context=ctxt)
    #     _create_aggregate_with_hosts(context=ctxt, values=values2,
    #             hosts=a2_hosts, metadata=a2_metadata)
    #     a3 = _create_aggregate_with_hosts(context=ctxt, values=values3,
    #             hosts=a3_hosts, metadata=a3_metadata)
    #     r1 = db.aggregate_metadata_get_by_host(ctxt, 'foo2.openstack.org',
    #                                            key='good')
    #     self.assertEqual(r1['good'], set(['value12', 'value23']))
    #     self.assertNotIn('fake_key1', r1)
    #     self.assertNotIn('bad', r1)
    #     # Delete metadata
    #     db.aggregate_metadata_delete(ctxt, a3['id'], 'good')
    #     r2 = db.aggregate_metadata_get_by_host(ctxt, 'foo3.openstack.org',
    #                                            key='good')
    #     self.assertNotIn('good', r2)

    def test_aggregate_get_by_host_not_found(self):
        ctxt = context.get_admin_context()
        _create_aggregate_with_hosts(context=ctxt)
        self.assertEqual([], db.aggregate_get_by_host(ctxt, 'unknown_host'))

    # def test_aggregate_delete_raise_not_found(self):
    #     ctxt = context.get_admin_context()
    #     # this does not exist!
    #     aggregate_id = 1
    #     self.assertRaises(exception.AggregateNotFound,
    #                       db.aggregate_delete,
    #                       ctxt, aggregate_id)

    # def test_aggregate_delete(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata=None)
    #     db.aggregate_delete(ctxt, result['id'])
    #     expected = db.aggregate_get_all(ctxt)
    #     self.assertEqual(0, len(expected))
    #     aggregate = db.aggregate_get(ctxt.elevated(read_deleted='yes'),
    #                                  result['id'])
    #     #NOTE(msimonin): deleted is set to 1 (not the id in ROME)
    #     #self.assertEqual(aggregate['deleted'], result['id'])
    #     self.assertEqual(aggregate['deleted'], 1)
    #
    # def test_aggregate_update(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata={'availability_zone':
    #         'fake_avail_zone'})
    #     self.assertEqual(result['availability_zone'], 'fake_avail_zone')
    #     new_values = _get_fake_aggr_values()
    #     new_values['availability_zone'] = 'different_avail_zone'
    #     updated = db.aggregate_update(ctxt, result['id'], new_values)
    #     self.assertNotEqual(result['availability_zone'],
    #                         updated['availability_zone'])
    #
    # def test_aggregate_update_with_metadata(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata=None)
    #     values = _get_fake_aggr_values()
    #     values['metadata'] = _get_fake_aggr_metadata()
    #     values['availability_zone'] = 'different_avail_zone'
    #     expected_metadata = copy.deepcopy(values['metadata'])
    #     expected_metadata['availability_zone'] = values['availability_zone']
    #     db.aggregate_update(ctxt, result['id'], values)
    #     metadata = db.aggregate_metadata_get(ctxt, result['id'])
    #     updated = db.aggregate_get(ctxt, result['id'])
    #     self.assertThat(metadata,
    #                     matchers.DictMatches(expected_metadata))
    #     self.assertNotEqual(result['availability_zone'],
    #                         updated['availability_zone'])
    #
    # def test_aggregate_update_with_existing_metadata(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     values = _get_fake_aggr_values()
    #     values['metadata'] = _get_fake_aggr_metadata()
    #     values['metadata']['fake_key1'] = 'foo'
    #     expected_metadata = copy.deepcopy(values['metadata'])
    #     db.aggregate_update(ctxt, result['id'], values)
    #     metadata = db.aggregate_metadata_get(ctxt, result['id'])
    #     self.assertThat(metadata, matchers.DictMatches(expected_metadata))
    #
    # def test_aggregate_update_zone_with_existing_metadata(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     new_zone = {'availability_zone': 'fake_avail_zone_2'}
    #     metadata = _get_fake_aggr_metadata()
    #     metadata.update(new_zone)
    #     db.aggregate_update(ctxt, result['id'], new_zone)
    #     expected = db.aggregate_metadata_get(ctxt, result['id'])
    #     self.assertThat(metadata, matchers.DictMatches(expected))
    #
    # def test_aggregate_update_raise_not_found(self):
    #     ctxt = context.get_admin_context()
    #     # this does not exist!
    #     aggregate_id = 1
    #     new_values = _get_fake_aggr_values()
    #     self.assertRaises(exception.AggregateNotFound,
    #                       db.aggregate_update, ctxt, aggregate_id, new_values)
    #
    # def test_aggregate_update_raise_name_exist(self):
    #     ctxt = context.get_admin_context()
    #     _create_aggregate(context=ctxt, values={'name': 'test1'},
    #                       metadata={'availability_zone': 'fake_avail_zone'})
    #     _create_aggregate(context=ctxt, values={'name': 'test2'},
    #                       metadata={'availability_zone': 'fake_avail_zone'})
    #     aggregate_id = 1
    #     new_values = {'name': 'test2'}
    #     self.assertRaises(exception.AggregateNameExists,
    #                       db.aggregate_update, ctxt, aggregate_id, new_values)
    #
    # def test_aggregate_get_all(self):
    #     ctxt = context.get_admin_context()
    #     counter = 3
    #     for c in range(counter):
    #         _create_aggregate(context=ctxt,
    #                           values={'name': 'fake_aggregate_%d' % c},
    #                           metadata=None)
    #     results = db.aggregate_get_all(ctxt)
    #     self.assertEqual(len(results), counter)
    #
    # def test_aggregate_get_all_non_deleted(self):
    #     ctxt = context.get_admin_context()
    #     add_counter = 5
    #     remove_counter = 2
    #     aggregates = []
    #     for c in range(1, add_counter):
    #         values = {'name': 'fake_aggregate_%d' % c}
    #         aggregates.append(_create_aggregate(context=ctxt,
    #                                             values=values, metadata=None))
    #     for c in range(1, remove_counter):
    #         db.aggregate_delete(ctxt, aggregates[c - 1]['id'])
    #     results = db.aggregate_get_all(ctxt)
    #     self.assertEqual(len(results), add_counter - remove_counter)
    #
    # def test_aggregate_metadata_add(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata=None)
    #     metadata = _get_fake_aggr_metadata()
    #     db.aggregate_metadata_add(ctxt, result['id'], metadata)
    #     expected = db.aggregate_metadata_get(ctxt, result['id'])
    #     self.assertThat(metadata, matchers.DictMatches(expected))
    #
    # def test_aggregate_metadata_add_empty_metadata(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata=None)
    #     metadata = {}
    #     db.aggregate_metadata_add(ctxt, result['id'], metadata)
    #     expected = db.aggregate_metadata_get(ctxt, result['id'])
    #     self.assertThat(metadata, matchers.DictMatches(expected))
    #
    # def test_aggregate_metadata_add_and_update(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     metadata = _get_fake_aggr_metadata()
    #     key = list(metadata.keys())[0]
    #     new_metadata = {key: 'foo',
    #                     'fake_new_key': 'fake_new_value'}
    #     metadata.update(new_metadata)
    #     db.aggregate_metadata_add(ctxt, result['id'], new_metadata)
    #     expected = db.aggregate_metadata_get(ctxt, result['id'])
    #     self.assertThat(metadata, matchers.DictMatches(expected))
    #
    # def test_aggregate_metadata_add_retry(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata=None)
    #
    #     def counted():
    #         def get_query(context, id, read_deleted):
    #             get_query.counter += 1
    #             raise db_exc.DBDuplicateEntry
    #         get_query.counter = 0
    #         return get_query
    #
    #     get_query = counted()
    #     self.stubs.Set(sqlalchemy_api,
    #                    '_aggregate_metadata_get_query', get_query)
    #     self.assertRaises(db_exc.DBDuplicateEntry, sqlalchemy_api.
    #                       aggregate_metadata_add, ctxt, result['id'], {},
    #                       max_retries=5)
    #     self.assertEqual(get_query.counter, 5)
    #
    # def test_aggregate_metadata_update(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     metadata = _get_fake_aggr_metadata()
    #     key = list(metadata.keys())[0]
    #     db.aggregate_metadata_delete(ctxt, result['id'], key)
    #     new_metadata = {key: 'foo'}
    #     db.aggregate_metadata_add(ctxt, result['id'], new_metadata)
    #     expected = db.aggregate_metadata_get(ctxt, result['id'])
    #     metadata[key] = 'foo'
    #     self.assertThat(metadata, matchers.DictMatches(expected))
    #
    # def test_aggregate_metadata_delete(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata=None)
    #     metadata = _get_fake_aggr_metadata()
    #     db.aggregate_metadata_add(ctxt, result['id'], metadata)
    #     db.aggregate_metadata_delete(ctxt, result['id'],
    #                                  list(metadata.keys())[0])
    #     expected = db.aggregate_metadata_get(ctxt, result['id'])
    #     del metadata[list(metadata.keys())[0]]
    #     self.assertThat(metadata, matchers.DictMatches(expected))
    #
    # def test_aggregate_remove_availability_zone(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt, metadata={'availability_zone':
    #         'fake_avail_zone'})
    #     db.aggregate_metadata_delete(ctxt, result['id'], 'availability_zone')
    #     expected = db.aggregate_metadata_get(ctxt, result['id'])
    #     aggregate = db.aggregate_get(ctxt, result['id'])
    #     self.assertIsNone(aggregate['availability_zone'])
    #     self.assertThat({}, matchers.DictMatches(expected))
    #
    # def test_aggregate_metadata_delete_raise_not_found(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     self.assertRaises(exception.AggregateMetadataNotFound,
    #                       db.aggregate_metadata_delete,
    #                       ctxt, result['id'], 'foo_key')
    #
    # def test_aggregate_host_add(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate_with_hosts(context=ctxt, metadata=None)
    #     expected = db.aggregate_host_get_all(ctxt, result['id'])
    #     self.assertEqual(_get_fake_aggr_hosts(), expected)
    #
    # def test_aggregate_host_re_add(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate_with_hosts(context=ctxt, metadata=None)
    #     host = _get_fake_aggr_hosts()[0]
    #     db.aggregate_host_delete(ctxt, result['id'], host)
    #     db.aggregate_host_add(ctxt, result['id'], host)
    #     expected = db.aggregate_host_get_all(ctxt, result['id'])
    #     self.assertEqual(len(expected), 1)
    #
    # def test_aggregate_host_add_duplicate_works(self):
    #     ctxt = context.get_admin_context()
    #     r1 = _create_aggregate_with_hosts(context=ctxt, metadata=None)
    #     r2 = _create_aggregate_with_hosts(ctxt,
    #                       values={'name': 'fake_aggregate2'},
    #                       metadata={'availability_zone': 'fake_avail_zone2'})
    #     h1 = db.aggregate_host_get_all(ctxt, r1['id'])
    #     h2 = db.aggregate_host_get_all(ctxt, r2['id'])
    #     self.assertEqual(h1, h2)
    #
    # def test_aggregate_host_add_duplicate_raise_exist_exc(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate_with_hosts(context=ctxt, metadata=None)
    #     self.assertRaises(exception.AggregateHostExists,
    #                       db.aggregate_host_add,
    #                       ctxt, result['id'], _get_fake_aggr_hosts()[0])
    #
    # def test_aggregate_host_add_raise_not_found(self):
    #     ctxt = context.get_admin_context()
    #     # this does not exist!
    #     aggregate_id = 1
    #     host = _get_fake_aggr_hosts()[0]
    #     self.assertRaises(exception.AggregateNotFound,
    #                       db.aggregate_host_add,
    #                       ctxt, aggregate_id, host)
    #
    # def test_aggregate_host_delete(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate_with_hosts(context=ctxt, metadata=None)
    #     db.aggregate_host_delete(ctxt, result['id'],
    #                              _get_fake_aggr_hosts()[0])
    #     expected = db.aggregate_host_get_all(ctxt, result['id'])
    #     self.assertEqual(0, len(expected))
    #
    # def test_aggregate_host_delete_raise_not_found(self):
    #     ctxt = context.get_admin_context()
    #     result = _create_aggregate(context=ctxt)
    #     self.assertRaises(exception.AggregateHostNotFound,
    #                       db.aggregate_host_delete,
    #                       ctxt, result['id'], _get_fake_aggr_hosts()[0])

