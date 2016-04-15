__author__ = 'msimonin'


import unittest
import uuid as stdlib_uuid
from nova.db.discovery import context
from nova import db
from nova import objects
objects.register_all()

class FixedIpTestCase(unittest.TestCase):

    def setUp(self):
        super(FixedIpTestCase, self).setUp()
        self.ctxt = context.get_admin_context()


    def _create_instance(self, **kwargs):
        instance = db.instance_create(self.ctxt, kwargs)
        return instance['uuid']

    def create_fixed_ip(self, **params):
        default_params = {'address': '192.168.0.1', 'virtual_interface_id':1}
        default_params.update(params)
        return db.fixed_ip_create(self.ctxt, default_params)['address']

    def _create_virt_interface(self, values):
        return db.virtual_interface_create(self.ctxt, values)

    def test_get_by_instance(self):
        instance_uuid = self._create_instance()
        network = db.network_create_safe(self.ctxt, {'label': 'mynetwork'})

        address = self.create_fixed_ip(network_id=network['id'])
        # associate the ip to the instance
        db.fixed_ip_associate(self.ctxt, address, instance_uuid,
                              network_id=network['id'])
        # associate a vif to its instance using this address
        self._create_virt_interface({
            'id': 1,
            'instance_uuid': instance_uuid,
            'address': 'fake_address',
            'network_id': network['id'],
            'uuid': str(stdlib_uuid.uuid4())
        })
        fixed_ip = db.fixed_ip_get_by_address(self.ctxt, address)
        fixedips = objects.FixedIPList.get_by_instance_uuid(self.ctxt, instance_uuid)
        self.assertEqual(1, len(fixedips))

        print("#####")
        print(fixedips)
        print("#####")


    def test_get_by_network(self):
        instance_uuid = self._create_instance()
        network = db.network_create_safe(self.ctxt, {'label': 'mynetwork'})

        address = self.create_fixed_ip(network_id=network['id'], host='myhost')
        # associate the ip to the instance
        db.fixed_ip_associate(self.ctxt, address, instance_uuid,
                              network_id=network['id'])
        # associate a vif to its instance using this address
        self._create_virt_interface({
            'id': 1,
            'instance_uuid': instance_uuid,
            'address': 'fake_address',
            'network_id': network['id'],
            'uuid': str(stdlib_uuid.uuid4())
        })
        fixedips = objects.FixedIPList.get_by_network(self.ctxt, network)
        print("#####")
        print(fixedips)
        print("#####")