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
from sqlalchemy.orm import query
from sqlalchemy import sql
from sqlalchemy import Table
import unittest

from nova import block_device
from nova.compute import arch
from nova.compute import task_states
from nova.compute import vm_states
from nova import context
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

CONF = cfg.CONF
CONF.import_opt('reserved_host_memory_mb', 'nova.compute.resource_tracker')
CONF.import_opt('reserved_host_disk_mb', 'nova.compute.resource_tracker')

get_engine = sqlalchemy_api.get_engine



import logging
logging.getLogger().setLevel(logging.DEBUG)

class ModelsObjectComparatorMixin(object):
    def _dict_from_object(self, obj, ignored_keys):
        if ignored_keys is None:
            ignored_keys = []

        return {k: v for k, v in obj.items()
                if k not in ignored_keys}

    def _assertEqualObjects(self, obj1, obj2, ignored_keys=None):
        obj1 = self._dict_from_object(obj1, ignored_keys)
        obj2 = self._dict_from_object(obj2, ignored_keys)

        self.assertEqual(len(obj1),
                         len(obj2),
                         "Keys mismatch: %s" %
                          str(set(obj1.keys()) ^ set(obj2.keys())))
        for key, value in obj1.items():
            self.assertEqual(value, obj2[key])

    def _assertEqualListsOfObjects(self, objs1, objs2, ignored_keys=None):
        obj_to_dict = lambda o: self._dict_from_object(o, ignored_keys)
        sort_key = lambda d: [d[k] for k in sorted(d)]
        conv_and_sort = lambda obj: sorted(map(obj_to_dict, obj), key=sort_key)

        self.assertEqual(conv_and_sort(objs1), conv_and_sort(objs2))

    def _assertEqualOrderedListOfObjects(self, objs1, objs2,
                                         ignored_keys=None):
        obj_to_dict = lambda o: self._dict_from_object(o, ignored_keys)
        conv = lambda objs: [obj_to_dict(obj) for obj in objs]

        self.assertEqual(conv(objs1), conv(objs2))

    def _assertEqualListsOfPrimitivesAsSets(self, primitives1, primitives2):
        self.assertEqual(len(primitives1), len(primitives2))
        for primitive in primitives1:
            self.assertIn(primitive, primitives2)

        for primitive in primitives2:
            self.assertIn(primitive, primitives1)


class InstanceTestCase(unittest.TestCase, ModelsObjectComparatorMixin):

    """Tests for db.api.instance_* methods."""

    sample_data = {
        'project_id': 'project1',
        'hostname': 'example.com',
        'host': 'h1',
        'node': 'n1',
        'metadata': {'mkey1': 'mval1', 'mkey2': 'mval2'},
        'system_metadata': {'smkey1': 'smval1', 'smkey2': 'smval2'},
        'info_cache': {'ckey': 'cvalue'},
    }

    def setUp(self):
        super(InstanceTestCase, self).setUp()
        self.ctxt = context.get_admin_context()

    def _assertEqualInstances(self, instance1, instance2):
        self._assertEqualObjects(instance1, instance2,
                ignored_keys=['metadata', 'system_metadata', 'info_cache',
                              'extra'])

    def _assertEqualListsOfInstances(self, list1, list2):
        self._assertEqualListsOfObjects(list1, list2,
                ignored_keys=['metadata', 'system_metadata', 'info_cache',
                              'extra'])

    def create_instance_with_args(self, **kwargs):
        if 'context' in kwargs:
            context = kwargs.pop('context')
        else:
            context = self.ctxt
        args = self.sample_data.copy()
        args.update(kwargs)
        return db.instance_create(context, args)

    def test_instance_create(self):
        instance = self.create_instance_with_args()
        self.assertTrue(uuidutils.is_uuid_like(instance['uuid']))

    def test_instance_create_with_object_values(self):
        values = {
            'access_ip_v4': netaddr.IPAddress('1.2.3.4'),
            'access_ip_v6': netaddr.IPAddress('::1'),
            }
        dt_keys = ('created_at', 'deleted_at', 'updated_at',
                   'launched_at', 'terminated_at')
        dt = timeutils.utcnow()
        dt_utc = dt.replace(tzinfo=iso8601.iso8601.Utc())
        for key in dt_keys:
            values[key] = dt_utc
        inst = db.instance_create(self.ctxt, values)
        self.assertEqual(inst['access_ip_v4'], '1.2.3.4')
        self.assertEqual(inst['access_ip_v6'], '::1')
        for key in dt_keys:
            self.assertEqual(inst[key], dt)

    def test_instance_update_with_object_values(self):
        values = {
            'access_ip_v4': netaddr.IPAddress('1.2.3.4'),
            'access_ip_v6': netaddr.IPAddress('::1'),
            }
        dt_keys = ('created_at', 'deleted_at', 'updated_at',
                   'launched_at', 'terminated_at')
        dt = timeutils.utcnow()
        dt_utc = dt.replace(tzinfo=iso8601.iso8601.Utc())
        for key in dt_keys:
            values[key] = dt_utc
        inst = db.instance_create(self.ctxt, {})
        inst = db.instance_update(self.ctxt, inst['uuid'], values)
        self.assertEqual(inst['access_ip_v4'], '1.2.3.4')
        self.assertEqual(inst['access_ip_v6'], '::1')
        for key in dt_keys:
            self.assertEqual(inst[key], dt)

    def test_instance_update_no_metadata_clobber(self):
        meta = {'foo': 'bar'}
        sys_meta = {'sfoo': 'sbar'}
        values = {
            'metadata': meta,
            'system_metadata': sys_meta,
            }
        inst = db.instance_create(self.ctxt, {})
        inst = db.instance_update(self.ctxt, inst['uuid'], values)
        self.assertEqual(meta, utils.metadata_to_dict(inst['metadata']))
        self.assertEqual(sys_meta,
                         utils.metadata_to_dict(inst['system_metadata']))

    def test_instance_get_all_with_meta(self):
        self.create_instance_with_args()
        for inst in db.instance_get_all(self.ctxt):
            meta = utils.metadata_to_dict(inst['metadata'])
            self.assertEqual(meta, self.sample_data['metadata'])
            sys_meta = utils.metadata_to_dict(inst['system_metadata'])
            self.assertEqual(sys_meta, self.sample_data['system_metadata'])

    def test_instance_update(self):
        instance = self.create_instance_with_args()
        metadata = {'host': 'bar', 'key2': 'wuff'}
        system_metadata = {'original_image_ref': 'baz'}
        # Update the metadata
        db.instance_update(self.ctxt, instance['uuid'], {'metadata': metadata,
                           'system_metadata': system_metadata})
        # Retrieve the user-provided metadata to ensure it was successfully
        # updated
        self.assertEqual(metadata,
                db.instance_metadata_get(self.ctxt, instance['uuid']))
        self.assertEqual(system_metadata,
                db.instance_system_metadata_get(self.ctxt, instance['uuid']))

    def test_instance_update_bad_str_dates(self):
        instance = self.create_instance_with_args()
        values = {'created_at': '123'}
        self.assertRaises(ValueError,
                          db.instance_update,
                          self.ctxt, instance['uuid'], values)

    def test_instance_update_good_str_dates(self):
        instance = self.create_instance_with_args()
        values = {'created_at': '2011-01-31T00:00:00.0'}
        actual = db.instance_update(self.ctxt, instance['uuid'], values)
        expected = datetime.datetime(2011, 1, 31)
        self.assertEqual(expected, actual["created_at"])

    # def test_create_instance_unique_hostname(self):
    #     context1 = context.RequestContext('user1', 'p1')
    #     context2 = context.RequestContext('user2', 'p2')
    #     self.create_instance_with_args(hostname='h1', project_id='p1')
    #
    #     # With scope 'global' any duplicate should fail, be it this project:
    #     self.flags(osapi_compute_unique_server_name_scope='global')
    #     self.assertRaises(exception.InstanceExists,
    #                       self.create_instance_with_args,
    #                       context=context1,
    #                       hostname='h1', project_id='p3')
    #     # or another:
    #     self.assertRaises(exception.InstanceExists,
    #                       self.create_instance_with_args,
    #                       context=context2,
    #                       hostname='h1', project_id='p2')
    #     # With scope 'project' a duplicate in the project should fail:
    #     self.flags(osapi_compute_unique_server_name_scope='project')
    #     self.assertRaises(exception.InstanceExists,
    #                       self.create_instance_with_args,
    #                       context=context1,
    #                       hostname='h1', project_id='p1')
    #     # With scope 'project' a duplicate in a different project should work:
    #     self.flags(osapi_compute_unique_server_name_scope='project')
    #     self.create_instance_with_args(context=context2, hostname='h2')
    #     self.flags(osapi_compute_unique_server_name_scope=None)
    #
    # def test_instance_get_all_by_filters_empty_list_filter(self):
    #     filters = {'uuid': []}
    #     instances = db.instance_get_all_by_filters_sort(self.ctxt, filters)
    #     self.assertEqual([], instances)
    #
    # @mock.patch('nova.db.sqlalchemy.api.undefer')
    # @mock.patch('nova.db.sqlalchemy.api.joinedload')
    # def test_instance_get_all_by_filters_extra_columns(self,
    #                                                    mock_joinedload,
    #                                                    mock_undefer):
    #     db.instance_get_all_by_filters_sort(
    #         self.ctxt, {},
    #         columns_to_join=['info_cache', 'extra.pci_requests'])
    #     mock_joinedload.assert_called_once_with('info_cache')
    #     mock_undefer.assert_called_once_with('extra.pci_requests')
    #
    # @mock.patch('nova.db.sqlalchemy.api.undefer')
    # @mock.patch('nova.db.sqlalchemy.api.joinedload')
    # def test_instance_get_active_by_window_extra_columns(self,
    #                                                      mock_joinedload,
    #                                                      mock_undefer):
    #     now = datetime.datetime(2013, 10, 10, 17, 16, 37, 156701)
    #     db.instance_get_active_by_window_joined(
    #         self.ctxt, now,
    #         columns_to_join=['info_cache', 'extra.pci_requests'])
    #     mock_joinedload.assert_called_once_with('info_cache')
    #     mock_undefer.assert_called_once_with('extra.pci_requests')
    #
    # def test_instance_get_all_by_filters_with_meta(self):
    #     self.create_instance_with_args()
    #     for inst in db.instance_get_all_by_filters(self.ctxt, {}):
    #         meta = utils.metadata_to_dict(inst['metadata'])
    #         self.assertEqual(meta, self.sample_data['metadata'])
    #         sys_meta = utils.metadata_to_dict(inst['system_metadata'])
    #         self.assertEqual(sys_meta, self.sample_data['system_metadata'])
    #
    # def test_instance_get_all_by_filters_without_meta(self):
    #     self.create_instance_with_args()
    #     result = db.instance_get_all_by_filters(self.ctxt, {},
    #                                             columns_to_join=[])
    #     for inst in result:
    #         meta = utils.metadata_to_dict(inst['metadata'])
    #         self.assertEqual(meta, {})
    #         sys_meta = utils.metadata_to_dict(inst['system_metadata'])
    #         self.assertEqual(sys_meta, {})
    #
    # def test_instance_get_all_by_filters(self):
    #     instances = [self.create_instance_with_args() for i in range(3)]
    #     filtered_instances = db.instance_get_all_by_filters(self.ctxt, {})
    #     self._assertEqualListsOfInstances(instances, filtered_instances)
    #
    # def test_instance_get_all_by_filters_zero_limit(self):
    #     self.create_instance_with_args()
    #     instances = db.instance_get_all_by_filters(self.ctxt, {}, limit=0)
    #     self.assertEqual([], instances)
    #
    # def test_instance_metadata_get_multi(self):
    #     uuids = [self.create_instance_with_args()['uuid'] for i in range(3)]
    #     with sqlalchemy_api.main_context_manager.reader.using(self.ctxt):
    #         meta = sqlalchemy_api._instance_metadata_get_multi(
    #             self.ctxt, uuids)
    #     for row in meta:
    #         self.assertIn(row['instance_uuid'], uuids)

    def test_instance_metadata_get_multi_no_uuids(self):
        self.mox.StubOutWithMock(query.Query, 'filter')
        self.mox.ReplayAll()
        with sqlalchemy_api.main_context_manager.reader.using(self.ctxt):
            sqlalchemy_api._instance_metadata_get_multi(self.ctxt, [])

    def test_instance_system_system_metadata_get_multi(self):
        uuids = [self.create_instance_with_args()['uuid'] for i in range(3)]
        # with sqlalchemy_api.main_context_manager.reader.using(self.ctxt):
        sys_meta = sqlalchemy_api._instance_system_metadata_get_multi(
            self.ctxt, uuids)
        for row in sys_meta:
            self.assertIn(row['instance_uuid'], uuids)

    def test_instance_system_metadata_get_multi_no_uuids(self):
        self.mox.StubOutWithMock(query.Query, 'filter')
        self.mox.ReplayAll()
        sqlalchemy_api._instance_system_metadata_get_multi(self.ctxt, [])

    def test_instance_get_all_by_filters_regex(self):
        i1 = self.create_instance_with_args(display_name='test1')
        i2 = self.create_instance_with_args(display_name='teeeest2')
        self.create_instance_with_args(display_name='diff')
        result = db.instance_get_all_by_filters(self.ctxt,
                                                {'display_name': 't.*st.'})
        self._assertEqualListsOfInstances(result, [i1, i2])

    def test_instance_get_all_by_filters_changes_since(self):
        i1 = self.create_instance_with_args(updated_at=
                                            '2013-12-05T15:03:25.000000')
        i2 = self.create_instance_with_args(updated_at=
                                            '2013-12-05T15:03:26.000000')
        changes_since = iso8601.parse_date('2013-12-05T15:03:25.000000')
        result = db.instance_get_all_by_filters(self.ctxt,
                                                {'changes-since':
                                                 changes_since})
        self._assertEqualListsOfInstances([i1, i2], result)

        changes_since = iso8601.parse_date('2013-12-05T15:03:26.000000')
        result = db.instance_get_all_by_filters(self.ctxt,
                                                {'changes-since':
                                                 changes_since})
        self._assertEqualListsOfInstances([i2], result)

        db.instance_destroy(self.ctxt, i1['uuid'])
        filters = {}
        filters['changes-since'] = changes_since
        filters['marker'] = i1['uuid']
        result = db.instance_get_all_by_filters(self.ctxt,
                                                filters)
        self._assertEqualListsOfInstances([i2], result)

    def test_instance_get_all_by_filters_exact_match(self):
        instance = self.create_instance_with_args(host='host1')
        self.create_instance_with_args(host='host12')
        result = db.instance_get_all_by_filters(self.ctxt,
                                                {'host': 'host1'})
        self._assertEqualListsOfInstances([instance], result)

    def test_instance_get_all_by_filters_metadata(self):
        instance = self.create_instance_with_args(metadata={'foo': 'bar'})
        self.create_instance_with_args()
        result = db.instance_get_all_by_filters(self.ctxt,
                                                {'metadata': {'foo': 'bar'}})
        self._assertEqualListsOfInstances([instance], result)

    def test_instance_get_all_by_filters_system_metadata(self):
        instance = self.create_instance_with_args(
                system_metadata={'foo': 'bar'})
        self.create_instance_with_args()
        result = db.instance_get_all_by_filters(self.ctxt,
                {'system_metadata': {'foo': 'bar'}})
        self._assertEqualListsOfInstances([instance], result)

    def test_instance_get_all_by_filters_unicode_value(self):
        i1 = self.create_instance_with_args(display_name=u'test♥')
        i2 = self.create_instance_with_args(display_name=u'test')
        i3 = self.create_instance_with_args(display_name=u'test♥test')
        self.create_instance_with_args(display_name='diff')
        result = db.instance_get_all_by_filters(self.ctxt,
                                                {'display_name': u'test'})
        self._assertEqualListsOfInstances([i1, i2, i3], result)

        result = db.instance_get_all_by_filters(self.ctxt,
                                                {'display_name': u'test♥'})
        self._assertEqualListsOfInstances(result, [i1, i3])

    # def test_instance_get_all_by_filters_tags(self):
    #     instance = self.create_instance_with_args(
    #         metadata={'foo': 'bar'})
    #     self.create_instance_with_args()
    #     # For format 'tag-'
    #     result = db.instance_get_all_by_filters(
    #         self.ctxt, {'filter': [
    #             {'name': 'tag-key', 'value': 'foo'},
    #             {'name': 'tag-value', 'value': 'bar'},
    #         ]})
    #     self._assertEqualListsOfInstances([instance], result)
    #     # For format 'tag:'
    #     result = db.instance_get_all_by_filters(
    #         self.ctxt, {'filter': [
    #             {'name': 'tag:foo', 'value': 'bar'},
    #         ]})
    #     self._assertEqualListsOfInstances([instance], result)
    #     # For non-existent tag
    #     result = db.instance_get_all_by_filters(
    #         self.ctxt, {'filter': [
    #             {'name': 'tag:foo', 'value': 'barred'},
    #         ]})
    #     self.assertEqual([], result)
    #
    #     # Confirm with deleted tags
    #     db.instance_metadata_delete(self.ctxt, instance['uuid'], 'foo')
    #     # For format 'tag-'
    #     result = db.instance_get_all_by_filters(
    #         self.ctxt, {'filter': [
    #             {'name': 'tag-key', 'value': 'foo'},
    #         ]})
    #     self.assertEqual([], result)
    #     result = db.instance_get_all_by_filters(
    #         self.ctxt, {'filter': [
    #             {'name': 'tag-value', 'value': 'bar'}
    #         ]})
    #     self.assertEqual([], result)
    #     # For format 'tag:'
    #     result = db.instance_get_all_by_filters(
    #         self.ctxt, {'filter': [
    #             {'name': 'tag:foo', 'value': 'bar'},
    #         ]})
    #     self.assertEqual([], result)
    #
    # def test_instance_get_by_uuid(self):
    #     inst = self.create_instance_with_args()
    #     result = db.instance_get_by_uuid(self.ctxt, inst['uuid'])
    #     self._assertEqualInstances(inst, result)
    #
    # def test_instance_get_by_uuid_join_empty(self):
    #     inst = self.create_instance_with_args()
    #     result = db.instance_get_by_uuid(self.ctxt, inst['uuid'],
    #             columns_to_join=[])
    #     meta = utils.metadata_to_dict(result['metadata'])
    #     self.assertEqual(meta, {})
    #     sys_meta = utils.metadata_to_dict(result['system_metadata'])
    #     self.assertEqual(sys_meta, {})
    #
    # def test_instance_get_by_uuid_join_meta(self):
    #     inst = self.create_instance_with_args()
    #     result = db.instance_get_by_uuid(self.ctxt, inst['uuid'],
    #                 columns_to_join=['metadata'])
    #     meta = utils.metadata_to_dict(result['metadata'])
    #     self.assertEqual(meta, self.sample_data['metadata'])
    #     sys_meta = utils.metadata_to_dict(result['system_metadata'])
    #     self.assertEqual(sys_meta, {})
    #
    # def test_instance_get_by_uuid_join_sys_meta(self):
    #     inst = self.create_instance_with_args()
    #     result = db.instance_get_by_uuid(self.ctxt, inst['uuid'],
    #             columns_to_join=['system_metadata'])
    #     meta = utils.metadata_to_dict(result['metadata'])
    #     self.assertEqual(meta, {})
    #     sys_meta = utils.metadata_to_dict(result['system_metadata'])
    #     self.assertEqual(sys_meta, self.sample_data['system_metadata'])
    #
    # def test_instance_get_all_by_filters_deleted(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args(reservation_id='b')
    #     db.instance_destroy(self.ctxt, inst1['uuid'])
    #     result = db.instance_get_all_by_filters(self.ctxt, {})
    #     self._assertEqualListsOfObjects([inst1, inst2], result,
    #         ignored_keys=['metadata', 'system_metadata',
    #                       'deleted', 'deleted_at', 'info_cache',
    #                       'pci_devices', 'extra'])
    #
    # def test_instance_get_all_by_filters_deleted_and_soft_deleted(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args(vm_state=vm_states.SOFT_DELETED)
    #     self.create_instance_with_args()
    #     db.instance_destroy(self.ctxt, inst1['uuid'])
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'deleted': True})
    #     self._assertEqualListsOfObjects([inst1, inst2], result,
    #         ignored_keys=['metadata', 'system_metadata',
    #                       'deleted', 'deleted_at', 'info_cache',
    #                       'pci_devices', 'extra'])
    #
    # def test_instance_get_all_by_filters_deleted_no_soft_deleted(self):
    #     inst1 = self.create_instance_with_args()
    #     self.create_instance_with_args(vm_state=vm_states.SOFT_DELETED)
    #     self.create_instance_with_args()
    #     db.instance_destroy(self.ctxt, inst1['uuid'])
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'deleted': True,
    #                                              'soft_deleted': False})
    #     self._assertEqualListsOfObjects([inst1], result,
    #             ignored_keys=['deleted', 'deleted_at', 'metadata',
    #                           'system_metadata', 'info_cache', 'pci_devices',
    #                           'extra'])
    #
    # def test_instance_get_all_by_filters_alive_and_soft_deleted(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args(vm_state=vm_states.SOFT_DELETED)
    #     inst3 = self.create_instance_with_args()
    #     db.instance_destroy(self.ctxt, inst1['uuid'])
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'deleted': False,
    #                                              'soft_deleted': True})
    #     self._assertEqualListsOfInstances([inst2, inst3], result)
    #
    # def test_instance_get_all_by_filters_not_deleted(self):
    #     inst1 = self.create_instance_with_args()
    #     self.create_instance_with_args(vm_state=vm_states.SOFT_DELETED)
    #     inst3 = self.create_instance_with_args()
    #     inst4 = self.create_instance_with_args(vm_state=vm_states.ACTIVE)
    #     db.instance_destroy(self.ctxt, inst1['uuid'])
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'deleted': False})
    #     self.assertIsNone(inst3.vm_state)
    #     self._assertEqualListsOfInstances([inst3, inst4], result)
    #
    # def test_instance_get_all_by_filters_cleaned(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args(reservation_id='b')
    #     db.instance_update(self.ctxt, inst1['uuid'], {'cleaned': 1})
    #     result = db.instance_get_all_by_filters(self.ctxt, {})
    #     self.assertEqual(2, len(result))
    #     self.assertIn(inst1['uuid'], [result[0]['uuid'], result[1]['uuid']])
    #     self.assertIn(inst2['uuid'], [result[0]['uuid'], result[1]['uuid']])
    #     if inst1['uuid'] == result[0]['uuid']:
    #         self.assertTrue(result[0]['cleaned'])
    #         self.assertFalse(result[1]['cleaned'])
    #     else:
    #         self.assertTrue(result[1]['cleaned'])
    #         self.assertFalse(result[0]['cleaned'])
    #
    # def test_instance_get_all_by_filters_tag_any(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args()
    #     inst3 = self.create_instance_with_args()
    #
    #     t1 = u'tag1'
    #     t2 = u'tag2'
    #     t3 = u'tag3'
    #
    #     db.instance_tag_set(self.ctxt, inst1.uuid, [t1])
    #     db.instance_tag_set(self.ctxt, inst2.uuid, [t1, t2, t3])
    #     db.instance_tag_set(self.ctxt, inst3.uuid, [t3])
    #
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'tags-any': [t1, t2]})
    #     self._assertEqualListsOfObjects([inst1, inst2], result,
    #             ignored_keys=['deleted', 'deleted_at', 'metadata', 'extra',
    #                           'system_metadata', 'info_cache', 'pci_devices'])
    #
    # def test_instance_get_all_by_filters_tag_any_empty(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args()
    #
    #     t1 = u'tag1'
    #     t2 = u'tag2'
    #     t3 = u'tag3'
    #     t4 = u'tag4'
    #
    #     db.instance_tag_set(self.ctxt, inst1.uuid, [t1])
    #     db.instance_tag_set(self.ctxt, inst2.uuid, [t1, t2])
    #
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'tags-any': [t3, t4]})
    #     self.assertEqual([], result)
    #
    # def test_instance_get_all_by_filters_tag(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args()
    #     inst3 = self.create_instance_with_args()
    #
    #     t1 = u'tag1'
    #     t2 = u'tag2'
    #     t3 = u'tag3'
    #
    #     db.instance_tag_set(self.ctxt, inst1.uuid, [t1, t3])
    #     db.instance_tag_set(self.ctxt, inst2.uuid, [t1, t2])
    #     db.instance_tag_set(self.ctxt, inst3.uuid, [t1, t2, t3])
    #
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'tags': [t1, t2]})
    #     self._assertEqualListsOfObjects([inst2, inst3], result,
    #             ignored_keys=['deleted', 'deleted_at', 'metadata', 'extra',
    #                           'system_metadata', 'info_cache', 'pci_devices'])
    #
    # def test_instance_get_all_by_filters_tag_empty(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args()
    #
    #     t1 = u'tag1'
    #     t2 = u'tag2'
    #     t3 = u'tag3'
    #
    #     db.instance_tag_set(self.ctxt, inst1.uuid, [t1])
    #     db.instance_tag_set(self.ctxt, inst2.uuid, [t1, t2])
    #
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'tags': [t3]})
    #     self.assertEqual([], result)
    #
    # def test_instance_get_all_by_filters_tag_any_and_tag(self):
    #     inst1 = self.create_instance_with_args()
    #     inst2 = self.create_instance_with_args()
    #     inst3 = self.create_instance_with_args()
    #
    #     t1 = u'tag1'
    #     t2 = u'tag2'
    #     t3 = u'tag3'
    #     t4 = u'tag4'
    #
    #     db.instance_tag_set(self.ctxt, inst1.uuid, [t1, t2])
    #     db.instance_tag_set(self.ctxt, inst2.uuid, [t1, t2, t4])
    #     db.instance_tag_set(self.ctxt, inst3.uuid, [t2, t3])
    #
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'tags': [t1, t2],
    #                                              'tags-any': [t3, t4]})
    #     self._assertEqualListsOfObjects([inst2], result,
    #             ignored_keys=['deleted', 'deleted_at', 'metadata', 'extra',
    #                           'system_metadata', 'info_cache', 'pci_devices'])
    #
    # def test_instance_get_all_by_filters_tags_and_project_id(self):
    #     context1 = context.RequestContext('user1', 'p1')
    #     context2 = context.RequestContext('user2', 'p2')
    #
    #     inst1 = self.create_instance_with_args(context=context1,
    #                                            project_id='p1')
    #     inst2 = self.create_instance_with_args(context=context1,
    #                                            project_id='p1')
    #     inst3 = self.create_instance_with_args(context=context2,
    #                                            project_id='p2')
    #     t1 = u'tag1'
    #     t2 = u'tag2'
    #     t3 = u'tag3'
    #     t4 = u'tag4'
    #
    #     db.instance_tag_set(context1, inst1.uuid, [t1, t2])
    #     db.instance_tag_set(context1, inst2.uuid, [t1, t2, t4])
    #     db.instance_tag_set(context2, inst3.uuid, [t1, t2, t3, t4])
    #
    #     result = db.instance_get_all_by_filters(self.ctxt,
    #                                             {'tags': [t1, t2],
    #                                              'tags-any': [t3, t4],
    #                                              'project_id': 'p1'})
    #     self._assertEqualListsOfObjects([inst2], result,
    #             ignored_keys=['deleted', 'deleted_at', 'metadata', 'extra',
    #                           'system_metadata', 'info_cache', 'pci_devices'])
    #
    # def test_instance_get_all_by_host_and_node_no_join(self):
    #     instance = self.create_instance_with_args()
    #     result = db.instance_get_all_by_host_and_node(self.ctxt, 'h1', 'n1')
    #     self.assertEqual(result[0]['uuid'], instance['uuid'])
    #     self.assertEqual(result[0]['system_metadata'], [])
    #
    # def test_instance_get_all_by_host_and_node(self):
    #     instance = self.create_instance_with_args(
    #         system_metadata={'foo': 'bar'})
    #     result = db.instance_get_all_by_host_and_node(
    #         self.ctxt, 'h1', 'n1',
    #         columns_to_join=['system_metadata', 'extra'])
    #     self.assertEqual(instance['uuid'], result[0]['uuid'])
    #     self.assertEqual('bar', result[0]['system_metadata'][0]['value'])
    #     self.assertEqual(instance['uuid'], result[0]['extra']['instance_uuid'])
    #
    # @mock.patch('nova.db.sqlalchemy.api._instances_fill_metadata')
    # @mock.patch('nova.db.sqlalchemy.api._instance_get_all_query')
    # def test_instance_get_all_by_host_and_node_fills_manually(self,
    #                                                           mock_getall,
    #                                                           mock_fill):
    #     db.instance_get_all_by_host_and_node(
    #         self.ctxt, 'h1', 'n1',
    #         columns_to_join=['metadata', 'system_metadata', 'extra', 'foo'])
    #     self.assertEqual(sorted(['extra', 'foo']),
    #                      sorted(mock_getall.call_args[1]['joins']))
    #     self.assertEqual(sorted(['metadata', 'system_metadata']),
    #                      sorted(mock_fill.call_args[1]['manual_joins']))
    #
    # def _get_base_values(self):
    #     return {
    #         'name': 'fake_sec_group',
    #         'description': 'fake_sec_group_descr',
    #         'user_id': 'fake',
    #         'project_id': 'fake',
    #         'instances': []
    #         }
    #
    # def _get_base_rule_values(self):
    #     return {
    #         'protocol': "tcp",
    #         'from_port': 80,
    #         'to_port': 8080,
    #         'cidr': None,
    #         'deleted': 0,
    #         'deleted_at': None,
    #         'grantee_group': None,
    #         'updated_at': None
    #         }
    #
    # def _create_security_group(self, values):
    #     v = self._get_base_values()
    #     v.update(values)
    #     return db.security_group_create(self.ctxt, v)
    #
    # def _create_security_group_rule(self, values):
    #     v = self._get_base_rule_values()
    #     v.update(values)
    #     return db.security_group_rule_create(self.ctxt, v)
    #
    # def test_instance_get_all_by_grantee_security_groups(self):
    #     instance1 = self.create_instance_with_args()
    #     instance2 = self.create_instance_with_args()
    #     instance3 = self.create_instance_with_args()
    #     secgroup1 = self._create_security_group(
    #         {'name': 'fake-secgroup1', 'instances': [instance1]})
    #     secgroup2 = self._create_security_group(
    #         {'name': 'fake-secgroup2', 'instances': [instance1]})
    #     secgroup3 = self._create_security_group(
    #         {'name': 'fake-secgroup3', 'instances': [instance2]})
    #     secgroup4 = self._create_security_group(
    #         {'name': 'fake-secgroup4', 'instances': [instance2, instance3]})
    #     self._create_security_group_rule({'grantee_group': secgroup1,
    #                                       'parent_group': secgroup3})
    #     self._create_security_group_rule({'grantee_group': secgroup2,
    #                                       'parent_group': secgroup4})
    #     group_ids = [secgroup['id'] for secgroup in [secgroup1, secgroup2]]
    #     instances = db.instance_get_all_by_grantee_security_groups(self.ctxt,
    #                                                                group_ids)
    #     instance_uuids = [instance['uuid'] for instance in instances]
    #     self.assertEqual(len(instances), 2)
    #     self.assertIn(instance2['uuid'], instance_uuids)
    #     self.assertIn(instance3['uuid'], instance_uuids)
    #
    # def test_instance_get_all_by_grantee_security_groups_empty_group_ids(self):
    #     results = db.instance_get_all_by_grantee_security_groups(self.ctxt, [])
    #     self.assertEqual([], results)
    #
    # def test_instance_get_all_hung_in_rebooting(self):
    #     # Ensure no instances are returned.
    #     results = db.instance_get_all_hung_in_rebooting(self.ctxt, 10)
    #     self.assertEqual([], results)
    #
    #     # Ensure one rebooting instance with updated_at older than 10 seconds
    #     # is returned.
    #     instance = self.create_instance_with_args(task_state="rebooting",
    #             updated_at=datetime.datetime(2000, 1, 1, 12, 0, 0))
    #     results = db.instance_get_all_hung_in_rebooting(self.ctxt, 10)
    #     self._assertEqualListsOfObjects([instance], results,
    #         ignored_keys=['task_state', 'info_cache', 'security_groups',
    #                       'metadata', 'system_metadata', 'pci_devices',
    #                       'extra'])
    #     db.instance_update(self.ctxt, instance['uuid'], {"task_state": None})
    #
    #     # Ensure the newly rebooted instance is not returned.
    #     self.create_instance_with_args(task_state="rebooting",
    #                                    updated_at=timeutils.utcnow())
    #     results = db.instance_get_all_hung_in_rebooting(self.ctxt, 10)
    #     self.assertEqual([], results)

    def test_instance_update_with_expected_vm_state(self):
        instance = self.create_instance_with_args(vm_state='foo')
        db.instance_update(self.ctxt, instance['uuid'], {'host': 'h1',
                                       'expected_vm_state': ('foo', 'bar')})

    def test_instance_update_with_unexpected_vm_state(self):
        instance = self.create_instance_with_args(vm_state='foo')
        self.assertRaises(exception.InstanceUpdateConflict,
                    db.instance_update, self.ctxt, instance['uuid'],
                    {'host': 'h1', 'expected_vm_state': ('spam', 'bar')})

    def test_instance_update_with_instance_uuid(self):
        # test instance_update() works when an instance UUID is passed.
        ctxt = context.get_admin_context()

        # Create an instance with some metadata
        values = {'metadata': {'host': 'foo', 'key1': 'meow'},
                  'system_metadata': {'original_image_ref': 'blah'}}
        instance = db.instance_create(ctxt, values)

        # Update the metadata
        values = {'metadata': {'host': 'bar', 'key2': 'wuff'},
                  'system_metadata': {'original_image_ref': 'baz'}}
        db.instance_update(ctxt, instance['uuid'], values)

        # Retrieve the user-provided metadata to ensure it was successfully
        # updated
        instance_meta = db.instance_metadata_get(ctxt, instance['uuid'])
        self.assertEqual('bar', instance_meta['host'])
        self.assertEqual('wuff', instance_meta['key2'])
        self.assertNotIn('key1', instance_meta)

        # Retrieve the system metadata to ensure it was successfully updated
        system_meta = db.instance_system_metadata_get(ctxt, instance['uuid'])
        self.assertEqual('baz', system_meta['original_image_ref'])

    def test_delete_instance_metadata_on_instance_destroy(self):
        ctxt = context.get_admin_context()
        # Create an instance with some metadata
        values = {'metadata': {'host': 'foo', 'key1': 'meow'},
                  'system_metadata': {'original_image_ref': 'blah'}}
        instance = db.instance_create(ctxt, values)
        instance_meta = db.instance_metadata_get(ctxt, instance['uuid'])
        self.assertEqual('foo', instance_meta['host'])
        self.assertEqual('meow', instance_meta['key1'])
        db.instance_destroy(ctxt, instance['uuid'])
        instance_meta = db.instance_metadata_get(ctxt, instance['uuid'])
        # Make sure instance metadata is deleted as well
        self.assertEqual({}, instance_meta)

    def test_delete_instance_faults_on_instance_destroy(self):
        ctxt = context.get_admin_context()
        uuid = str(stdlib_uuid.uuid4())
        # Create faults
        db.instance_create(ctxt, {'uuid': uuid})

        fault_values = {
            'message': 'message',
            'details': 'detail',
            'instance_uuid': uuid,
            'code': 404,
            'host': 'localhost'
        }
        fault = db.instance_fault_create(ctxt, fault_values)

        # Retrieve the fault to ensure it was successfully added
        faults = db.instance_fault_get_by_instance_uuids(ctxt, [uuid])
        self.assertEqual(1, len(faults[uuid]))
        self._assertEqualObjects(fault, faults[uuid][0])
        db.instance_destroy(ctxt, uuid)
        faults = db.instance_fault_get_by_instance_uuids(ctxt, [uuid])
        # Make sure instance faults is deleted as well
        self.assertEqual(0, len(faults[uuid]))

    def test_instance_update_and_get_original(self):
        instance = self.create_instance_with_args(vm_state='building')
        (old_ref, new_ref) = db.instance_update_and_get_original(self.ctxt,
                            instance['uuid'], {'vm_state': 'needscoffee'})
        self.assertEqual('building', old_ref['vm_state'])
        self.assertEqual('needscoffee', new_ref['vm_state'])

    # def test_instance_update_and_get_original_metadata(self):
    #     instance = self.create_instance_with_args()
    #     columns_to_join = ['metadata']
    #     (old_ref, new_ref) = db.instance_update_and_get_original(
    #         self.ctxt, instance['uuid'], {'vm_state': 'needscoffee'},
    #         columns_to_join=columns_to_join)
    #     meta = utils.metadata_to_dict(new_ref['metadata'])
    #     self.assertEqual(meta, self.sample_data['metadata'])
    #     sys_meta = utils.metadata_to_dict(new_ref['system_metadata'])
    #     self.assertEqual(sys_meta, {})
    #
    # def test_instance_update_and_get_original_metadata_none_join(self):
    #     instance = self.create_instance_with_args()
    #     (old_ref, new_ref) = db.instance_update_and_get_original(
    #         self.ctxt, instance['uuid'], {'metadata': {'mk1': 'mv3'}})
    #     meta = utils.metadata_to_dict(new_ref['metadata'])
    #     self.assertEqual(meta, {'mk1': 'mv3'})
    #
    # def test_instance_update_and_get_original_no_conflict_on_session(self):
    #     with sqlalchemy_api.main_context_manager.writer.using(self.ctxt):
    #         instance = self.create_instance_with_args()
    #         (old_ref, new_ref) = db.instance_update_and_get_original(
    #             self.ctxt, instance['uuid'], {'metadata': {'mk1': 'mv3'}})
    #
    #         # test some regular persisted fields
    #         self.assertEqual(old_ref.uuid, new_ref.uuid)
    #         self.assertEqual(old_ref.project_id, new_ref.project_id)
    #
    #         # after a copy operation, we can assert:
    #
    #         # 1. the two states have their own InstanceState
    #         old_insp = inspect(old_ref)
    #         new_insp = inspect(new_ref)
    #         self.assertNotEqual(old_insp, new_insp)
    #
    #         # 2. only one of the objects is still in our Session
    #         self.assertIs(new_insp.session, self.ctxt.session)
    #         self.assertIsNone(old_insp.session)
    #
    #         # 3. The "new" object remains persistent and ready
    #         # for updates
    #         self.assertTrue(new_insp.persistent)
    #
    #         # 4. the "old" object is detached from this Session.
    #         self.assertTrue(old_insp.detached)
    #
    # def test_instance_update_and_get_original_conflict_race(self):
    #     # Ensure that we retry if update_on_match fails for no discernable
    #     # reason
    #     instance = self.create_instance_with_args()
    #
    #     orig_update_on_match = update_match.update_on_match
    #
    #     # Reproduce the conditions of a race between fetching and updating the
    #     # instance by making update_on_match fail for no discernable reason the
    #     # first time it is called, but work normally the second time.
    #     with mock.patch.object(update_match, 'update_on_match',
    #                     side_effect=[update_match.NoRowsMatched,
    #                                  orig_update_on_match]):
    #         db.instance_update_and_get_original(
    #             self.ctxt, instance['uuid'], {'metadata': {'mk1': 'mv3'}})
    #         self.assertEqual(update_match.update_on_match.call_count, 2)
    #
    # def test_instance_update_and_get_original_conflict_race_fallthrough(self):
    #     # Ensure that is update_match continuously fails for no discernable
    #     # reason, we evantually raise UnknownInstanceUpdateConflict
    #     instance = self.create_instance_with_args()
    #
    #     # Reproduce the conditions of a race between fetching and updating the
    #     # instance by making update_on_match fail for no discernable reason.
    #     with mock.patch.object(update_match, 'update_on_match',
    #                     side_effect=update_match.NoRowsMatched):
    #         self.assertRaises(exception.UnknownInstanceUpdateConflict,
    #                           db.instance_update_and_get_original,
    #                           self.ctxt,
    #                           instance['uuid'],
    #                           {'metadata': {'mk1': 'mv3'}})
    #
    # def test_instance_update_and_get_original_expected_host(self):
    #     # Ensure that we allow update when expecting a host field
    #     instance = self.create_instance_with_args()
    #
    #     (orig, new) = db.instance_update_and_get_original(
    #         self.ctxt, instance['uuid'], {'host': None},
    #         expected={'host': 'h1'})
    #
    #     self.assertIsNone(new['host'])
    #
    # def test_instance_update_and_get_original_expected_host_fail(self):
    #     # Ensure that we detect a changed expected host and raise
    #     # InstanceUpdateConflict
    #     instance = self.create_instance_with_args()
    #
    #     try:
    #         db.instance_update_and_get_original(
    #             self.ctxt, instance['uuid'], {'host': None},
    #             expected={'host': 'h2'})
    #     except exception.InstanceUpdateConflict as ex:
    #         self.assertEqual(ex.kwargs['instance_uuid'], instance['uuid'])
    #         self.assertEqual(ex.kwargs['actual'], {'host': 'h1'})
    #         self.assertEqual(ex.kwargs['expected'], {'host': ['h2']})
    #     else:
    #         self.fail('InstanceUpdateConflict was not raised')
    #
    # def test_instance_update_and_get_original_expected_host_none(self):
    #     # Ensure that we allow update when expecting a host field of None
    #     instance = self.create_instance_with_args(host=None)
    #
    #     (old, new) = db.instance_update_and_get_original(
    #         self.ctxt, instance['uuid'], {'host': 'h1'},
    #         expected={'host': None})
    #     self.assertEqual('h1', new['host'])
    #
    # def test_instance_update_and_get_original_expected_host_none_fail(self):
    #     # Ensure that we detect a changed expected host of None and raise
    #     # InstanceUpdateConflict
    #     instance = self.create_instance_with_args()
    #
    #     try:
    #         db.instance_update_and_get_original(
    #             self.ctxt, instance['uuid'], {'host': None},
    #             expected={'host': None})
    #     except exception.InstanceUpdateConflict as ex:
    #         self.assertEqual(ex.kwargs['instance_uuid'], instance['uuid'])
    #         self.assertEqual(ex.kwargs['actual'], {'host': 'h1'})
    #         self.assertEqual(ex.kwargs['expected'], {'host': [None]})
    #     else:
    #         self.fail('InstanceUpdateConflict was not raised')
    #
    # def test_instance_update_and_get_original_expected_task_state_single_fail(self):  # noqa
    #     # Ensure that we detect a changed expected task and raise
    #     # UnexpectedTaskStateError
    #     instance = self.create_instance_with_args()
    #
    #     try:
    #         db.instance_update_and_get_original(
    #             self.ctxt, instance['uuid'], {
    #                 'host': None,
    #                 'expected_task_state': task_states.SCHEDULING
    #             })
    #     except exception.UnexpectedTaskStateError as ex:
    #         self.assertEqual(ex.kwargs['instance_uuid'], instance['uuid'])
    #         self.assertEqual(ex.kwargs['actual'], {'task_state': None})
    #         self.assertEqual(ex.kwargs['expected'],
    #                          {'task_state': [task_states.SCHEDULING]})
    #     else:
    #         self.fail('UnexpectedTaskStateError was not raised')
    #
    # def test_instance_update_and_get_original_expected_task_state_single_pass(self):  # noqa
    #     # Ensure that we allow an update when expected task is correct
    #     instance = self.create_instance_with_args()
    #
    #     (orig, new) = db.instance_update_and_get_original(
    #         self.ctxt, instance['uuid'], {
    #             'host': None,
    #             'expected_task_state': None
    #         })
    #     self.assertIsNone(new['host'])
    #
    # def test_instance_update_and_get_original_expected_task_state_multi_fail(self):  # noqa
    #     # Ensure that we detect a changed expected task and raise
    #     # UnexpectedTaskStateError when there are multiple potential expected
    #     # tasks
    #     instance = self.create_instance_with_args()
    #
    #     try:
    #         db.instance_update_and_get_original(
    #             self.ctxt, instance['uuid'], {
    #                 'host': None,
    #                 'expected_task_state': [task_states.SCHEDULING,
    #                                         task_states.REBUILDING]
    #             })
    #     except exception.UnexpectedTaskStateError as ex:
    #         self.assertEqual(ex.kwargs['instance_uuid'], instance['uuid'])
    #         self.assertEqual(ex.kwargs['actual'], {'task_state': None})
    #         self.assertEqual(ex.kwargs['expected'],
    #                          {'task_state': [task_states.SCHEDULING,
    #                                           task_states.REBUILDING]})
    #     else:
    #         self.fail('UnexpectedTaskStateError was not raised')
    #
    # def test_instance_update_and_get_original_expected_task_state_multi_pass(self):  # noqa
    #     # Ensure that we allow an update when expected task is in a list of
    #     # expected tasks
    #     instance = self.create_instance_with_args()
    #
    #     (orig, new) = db.instance_update_and_get_original(
    #         self.ctxt, instance['uuid'], {
    #             'host': None,
    #             'expected_task_state': [task_states.SCHEDULING, None]
    #         })
    #     self.assertIsNone(new['host'])
    #
    # def test_instance_update_and_get_original_expected_task_state_deleting(self):  # noqa
    #     # Ensure that we raise UnepectedDeletingTaskStateError when task state
    #     # is not as expected, and it is DELETING
    #     instance = self.create_instance_with_args(
    #         task_state=task_states.DELETING)
    #
    #     try:
    #         db.instance_update_and_get_original(
    #             self.ctxt, instance['uuid'], {
    #                 'host': None,
    #                 'expected_task_state': task_states.SCHEDULING
    #             })
    #     except exception.UnexpectedDeletingTaskStateError as ex:
    #         self.assertEqual(ex.kwargs['instance_uuid'], instance['uuid'])
    #         self.assertEqual(ex.kwargs['actual'],
    #                          {'task_state': task_states.DELETING})
    #         self.assertEqual(ex.kwargs['expected'],
    #                          {'task_state': [task_states.SCHEDULING]})
    #     else:
    #         self.fail('UnexpectedDeletingTaskStateError was not raised')
    #
    # def test_instance_update_unique_name(self):
    #     context1 = context.RequestContext('user1', 'p1')
    #     context2 = context.RequestContext('user2', 'p2')
    #
    #     inst1 = self.create_instance_with_args(context=context1,
    #                                            project_id='p1',
    #                                            hostname='fake_name1')
    #     inst2 = self.create_instance_with_args(context=context1,
    #                                            project_id='p1',
    #                                            hostname='fake_name2')
    #     inst3 = self.create_instance_with_args(context=context2,
    #                                            project_id='p2',
    #                                            hostname='fake_name3')
    #     # osapi_compute_unique_server_name_scope is unset so this should work:
    #     db.instance_update(context1, inst1['uuid'], {'hostname': 'fake_name2'})
    #     db.instance_update(context1, inst1['uuid'], {'hostname': 'fake_name1'})
    #
    #     # With scope 'global' any duplicate should fail.
    #     self.flags(osapi_compute_unique_server_name_scope='global')
    #     self.assertRaises(exception.InstanceExists,
    #                       db.instance_update,
    #                       context1,
    #                       inst2['uuid'],
    #                       {'hostname': 'fake_name1'})
    #     self.assertRaises(exception.InstanceExists,
    #                       db.instance_update,
    #                       context2,
    #                       inst3['uuid'],
    #                       {'hostname': 'fake_name1'})
    #     # But we should definitely be able to update our name if we aren't
    #     #  really changing it.
    #     db.instance_update(context1, inst1['uuid'], {'hostname': 'fake_NAME'})
    #
    #     # With scope 'project' a duplicate in the project should fail:
    #     self.flags(osapi_compute_unique_server_name_scope='project')
    #     self.assertRaises(exception.InstanceExists, db.instance_update,
    #                       context1, inst2['uuid'], {'hostname': 'fake_NAME'})
    #
    #     # With scope 'project' a duplicate in a different project should work:
    #     self.flags(osapi_compute_unique_server_name_scope='project')
    #     db.instance_update(context2, inst3['uuid'], {'hostname': 'fake_NAME'})
    #
    # def _test_instance_update_updates_metadata(self, metadata_type):
    #     instance = self.create_instance_with_args()
    #
    #     def set_and_check(meta):
    #         inst = db.instance_update(self.ctxt, instance['uuid'],
    #                            {metadata_type: dict(meta)})
    #         _meta = utils.metadata_to_dict(inst[metadata_type])
    #         self.assertEqual(meta, _meta)
    #
    #     meta = {'speed': '88', 'units': 'MPH'}
    #     set_and_check(meta)
    #     meta['gigawatts'] = '1.21'
    #     set_and_check(meta)
    #     del meta['gigawatts']
    #     set_and_check(meta)
    #     self.ctxt.read_deleted = 'yes'
    #     self.assertNotIn('gigawatts',
    #         db.instance_system_metadata_get(self.ctxt, instance.uuid))
    #
    # def test_security_group_in_use(self):
    #     db.instance_create(self.ctxt, dict(host='foo'))
    #
    # def test_instance_update_updates_system_metadata(self):
    #     # Ensure that system_metadata is updated during instance_update
    #     self._test_instance_update_updates_metadata('system_metadata')
    #
    # def test_instance_update_updates_metadata(self):
    #     # Ensure that metadata is updated during instance_update
    #     self._test_instance_update_updates_metadata('metadata')
    #
    # def test_instance_floating_address_get_all(self):
    #     ctxt = context.get_admin_context()
    #
    #     instance1 = db.instance_create(ctxt, {'host': 'h1', 'hostname': 'n1'})
    #     instance2 = db.instance_create(ctxt, {'host': 'h2', 'hostname': 'n2'})
    #
    #     fixed_addresses = ['1.1.1.1', '1.1.1.2', '1.1.1.3']
    #     float_addresses = ['2.1.1.1', '2.1.1.2', '2.1.1.3']
    #     instance_uuids = [instance1['uuid'], instance1['uuid'],
    #                       instance2['uuid']]
    #
    #     for fixed_addr, float_addr, instance_uuid in zip(fixed_addresses,
    #                                                      float_addresses,
    #                                                      instance_uuids):
    #         db.fixed_ip_create(ctxt, {'address': fixed_addr,
    #                                   'instance_uuid': instance_uuid})
    #         fixed_id = db.fixed_ip_get_by_address(ctxt, fixed_addr)['id']
    #         db.floating_ip_create(ctxt,
    #                               {'address': float_addr,
    #                                'fixed_ip_id': fixed_id})
    #
    #     real_float_addresses = \
    #             db.instance_floating_address_get_all(ctxt, instance_uuids[0])
    #     self.assertEqual(set(float_addresses[:2]), set(real_float_addresses))
    #     real_float_addresses = \
    #             db.instance_floating_address_get_all(ctxt, instance_uuids[2])
    #     self.assertEqual(set([float_addresses[2]]), set(real_float_addresses))
    #
    #     self.assertRaises(exception.InvalidUUID,
    #                       db.instance_floating_address_get_all,
    #                       ctxt, 'invalid_uuid')
    #
    # def test_instance_stringified_ips(self):
    #     instance = self.create_instance_with_args()
    #     instance = db.instance_update(
    #         self.ctxt, instance['uuid'],
    #         {'access_ip_v4': netaddr.IPAddress('1.2.3.4'),
    #          'access_ip_v6': netaddr.IPAddress('::1')})
    #     self.assertIsInstance(instance['access_ip_v4'], six.string_types)
    #     self.assertIsInstance(instance['access_ip_v6'], six.string_types)
    #     instance = db.instance_get_by_uuid(self.ctxt, instance['uuid'])
    #     self.assertIsInstance(instance['access_ip_v4'], six.string_types)
    #     self.assertIsInstance(instance['access_ip_v6'], six.string_types)
    #
    # @mock.patch('nova.db.sqlalchemy.api._check_instance_exists_in_project',
    #             return_value=None)
    # def test_instance_destroy(self, mock_check_inst_exists):
    #     ctxt = context.get_admin_context()
    #     values = {
    #         'metadata': {'key': 'value'},
    #         'system_metadata': {'key': 'value'}
    #     }
    #     inst_uuid = self.create_instance_with_args(**values)['uuid']
    #     db.instance_tag_set(ctxt, inst_uuid, [u'tag1', u'tag2'])
    #     db.instance_destroy(ctxt, inst_uuid)
    #
    #     self.assertRaises(exception.InstanceNotFound,
    #                       db.instance_get, ctxt, inst_uuid)
    #     self.assertIsNone(db.instance_info_cache_get(ctxt, inst_uuid))
    #     self.assertEqual({}, db.instance_metadata_get(ctxt, inst_uuid))
    #     self.assertEqual([], db.instance_tag_get_by_instance_uuid(
    #         ctxt, inst_uuid))
    #     ctxt.read_deleted = 'yes'
    #     self.assertEqual(values['system_metadata'],
    #                      db.instance_system_metadata_get(ctxt, inst_uuid))
    #
    # def test_instance_destroy_already_destroyed(self):
    #     ctxt = context.get_admin_context()
    #     instance = self.create_instance_with_args()
    #     db.instance_destroy(ctxt, instance['uuid'])
    #     self.assertRaises(exception.InstanceNotFound,
    #                       db.instance_destroy, ctxt, instance['uuid'])
    #
    # def test_check_instance_exists(self):
    #     instance = self.create_instance_with_args()
    #     with sqlalchemy_api.main_context_manager.reader.using(self.ctxt):
    #         self.assertIsNone(sqlalchemy_api._check_instance_exists_in_project(
    #             self.ctxt, instance['uuid']))
    #
    # def test_check_instance_exists_non_existing_instance(self):
    #     with sqlalchemy_api.main_context_manager.reader.using(self.ctxt):
    #         self.assertRaises(exception.InstanceNotFound,
    #                           sqlalchemy_api._check_instance_exists_in_project,
    #                           self.ctxt, '123')
    #
    # def test_check_instance_exists_from_different_tenant(self):
    #     context1 = context.RequestContext('user1', 'project1')
    #     context2 = context.RequestContext('user2', 'project2')
    #     instance = self.create_instance_with_args(context=context1)
    #     with sqlalchemy_api.main_context_manager.reader.using(context1):
    #         self.assertIsNone(sqlalchemy_api._check_instance_exists_in_project(
    #         context1, instance['uuid']))
    #
    #     with sqlalchemy_api.main_context_manager.reader.using(context2):
    #         self.assertRaises(exception.InstanceNotFound,
    #                           sqlalchemy_api._check_instance_exists_in_project,
    #                           context2, instance['uuid'])
    #
    # def test_check_instance_exists_admin_context(self):
    #     some_context = context.RequestContext('some_user', 'some_project')
    #     instance = self.create_instance_with_args(context=some_context)
    #
    #     with sqlalchemy_api.main_context_manager.reader.using(self.ctxt):
    #         # Check that method works correctly with admin context
    #         self.assertIsNone(sqlalchemy_api._check_instance_exists_in_project(
    #             self.ctxt, instance['uuid']))
