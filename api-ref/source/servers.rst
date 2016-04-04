
===================
 Servers (servers)
===================

Lists, creates, shows details for, updates, and deletes servers.

Concepts
========

Passwords
---------

When you create a server, you can specify a password through the
optional adminPass attribute. The password must meet the complexity
requirements set by your OpenStack Compute provider. The server might
enter an ERROR state if the complexity requirements are not met. In
this case, a client might issue a change password action to reset the
server password.

If you do not specify a password, the API generates and assigns a
random password that it returns in the response object. This password
meets the security requirements set by the compute provider. For
security reasons, subsequent GET calls do not require this password.

Server metadata
---------------

You can specify custom server metadata at server launch time. The
maximum size for each metadata key-value pair is 255 bytes. The
compute provider determines the maximum number of key-value pairs for
each server. You can query this value through the maxServerMeta
absolute limit.

Server networks
---------------

You can specify one or more networks to which the server connects at
launch time. Users can also specify a specific port on the network or
the fixed IP address to assign to the server interface.

You can use both IPv4 and IPv6 addresses as access addresses and you
can assign both addresses simultaneously. You can update access
addresses after you create a server.

Server personality
------------------

To customize the personality of a server instance, you can inject data
into its file system. For example, you might insert ssh keys, set
configuration files, or store data that you want to retrieve from
inside the instance. This customization method provides minimal
launch-time personalization. If you require significant customization,
create a custom image.

Follow these guidelines when you inject files:

The maximum size of the file path data is 255 bytes.

Encode the file contents as a Base64 string. The compute provider
determines the maximum size of the file contents. The image that you
use to create the server determines this value.

The maximum limit refers to the number of bytes in the decoded data
and not to the number of characters in the encoded data.

The maxPersonality absolute limit defines the maximum number of file
path and content pairs that you can supply. The compute provider
determines this value.

The maxPersonalitySize absolute limit is a byte limit that applies to
all images in the deployment. Providers can set additional per-image
personality limits.

The file injection might not occur until after the server builds and
boots.

After file injection, only system administrators can access
personality files. For example, on Linux, all files have root as the
owner and the root group as the group owner, and allow only user and
group read access (chmod 440).

Server access addresses
-----------------------

In a hybrid environment, the underlying implementation might not
control the IP address of a server. Instead, the access IP address
might be part of the dedicated hardware; for example, a router/NAT
device. In this case, you cannot use the addresses that the
implementation provides to access the server from outside the local
LAN. Instead, the API might assign a separate access address at
creation time to provide access to the server. This address might not
be directly bound to a network interface on the server and might not
necessarily appear when you query the server addresses. However,
clients should use an access address to access the server directly.


List servers - Lists IDs, names, and links for all servers.
===========================================================

.. rest_method:: GET /v2.1/{tenant_id}/servers

Servers contain a status attribute that indicates the current server
state. You can filter on the server status when you complete a list
servers request. The server status is returned in the response
body. The possible server status values are:

- ``ACTIVE``. The server is active.
- ``BUILDING``. The server has not finished the original build process.
- ``DELETED``. The server is permanently deleted.
- ``ERROR``. The server is in error.
- ``HARD_REBOOT``. The server is hard rebooting. This is equivalent to
  pulling the power plug on a physical server, plugging it back in,
  and rebooting it.
- ``MIGRATING``. The server is being migrated to a new host.
- ``PASSWORD``. The password is being reset on the server.
- ``PAUSED``. In a paused state, the state of the server is stored in
  RAM. A paused server continues to run in frozen state.
- ``REBOOT``. The server is in a soft reboot state. A reboot command
  was passed to the operating system.
- ``REBUILD``. The server is currently being rebuilt from an image.
- ``RESCUED``. The server is in rescue mode. A rescue image is running
  with the original server image attached.
- ``RESIZED``. Server is performing the differential copy of data that
  changed during its initial copy. Server is down for this stage.
- ``REVERT_RESIZE``. The resize or migration of a server failed for
  some reason. The destination server is being cleaned up and the
  original source server is restarting.
- ``SOFT_DELETED``. The server is marked as deleted but the disk
  images are still available to restore.
- ``STOPPED``. The server is powered off and the disk image still
  persists.
- ``SUSPENDED``. The server is suspended, either by request or
  necessity. This status appears for only the XenServer/XCP, KVM, and
  ESXi hypervisors. Administrative users can suspend an instance if it
  is infrequently used or to perform system maintenance. When you
  suspend an instance, its VM state is stored on disk, all memory is
  written to disk, and the virtual machine is stopped. Suspending an
  instance is similar to placing a device in hibernation; memory and
  vCPUs become available to create other instances.
- ``UNKNOWN``. The state of the server is unknown. Contact your cloud
  provider.
- ``VERIFY_RESIZE``. System is awaiting confirmation that the server
  is operational after a move or resize.

Normal response codes: 200

Error response codes: computeFault (400, 500, …), serviceUnavailable
(503), badRequest (400), unauthorized (401), forbidden (403),
badMethod (405)

Request parameters
------------------

.. rest_parameters:: parameters.yaml

  - tenant_id: tenant_id
  - changes-since: changes-since
  - image: image
  - flavor: flavor
  - name: name
  - status: status
  - host: host
  - limit: limit
  - marker: marker

Response Example
----------------

.. literalinclude:: /../../doc/api_samples/servers/servers-list-resp.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

  - x-openstack-request-id: request_id
  - servers: servers
  - id: server_id
  - links: generic_links
  - name: server_name


Create server
=============

.. rest_method:: POST /v2.1/{tenant_id}/servers

The progress of this operation depends on the location of the
requested image, network I/O, host load, selected flavor, and other
factors.

To check the progress of the request, make a GET /servers/{id}
request. This call returns a progress attribute, which is a percentage
value from 0 to 100.

The Location header returns the full URL to the newly created server
and is available as a self and bookmark link in the server
representation.

When you create a server, the response shows only the server ID, its
links, and the admin password. You can get additional attributes
through subsequent GET requests on the server.

Include the block-device-mapping-v2 parameter in the create request
body to boot a server from a volume.

Include the key_name parameter in the create request body to add a
keypair to the server when you create it. To create a keypair, make a
create keypair request.

Preconditions
-------------

The user must have sufficient server quota to create the number of
servers requested.

The connection to the Image service is valid.

Asynchronous postconditions
---------------------------

With correct permissions, you can see the server status as ACTIVE
through API calls.

With correct access, you can see the created server in the compute
node that OpenStack Compute manages.

Troubleshooting
---------------

If the server status remains BUILDING or shows another error status,
the request failed. Ensure you meet the preconditions then investigate
the compute node.

The server is not created in the compute node that OpenStack Compute
manages.

The compute node needs enough free resource to match the resource of
the server creation request.

Ensure that the scheduler selection filter can fulfill the request
with the available compute nodes that match the selection criteria of
the filter.

Normal response codes: 202

Error response codes: computeFault (400, 500, …), serviceUnavailable
(503), badRequest (400), unauthorized (401), forbidden (403),
badMethod (405), itemNotFound (404)

Request Example
---------------

.. literalinclude:: /../../doc/api_samples/servers/server-create-req.json
   :language: javascript

Request Parameters
------------------

.. rest_parameters:: parameters.yaml

   - tenant_id: tenant_id
   - server: server
   - security_groups: security_groups
   - user_data: user_data
   - os-availability-zone:availability_zone: availability_zone
   - imageRef: image_ref
   - flavorRef: flavor_ref
   - networks: network_obj
   - name: server_name
   - fixed_ip: fixed_ip
   - metadata: metadata
   - personality: personality
   - block_device_mapping_v2: block_device_mapping_v2
   - device_name: bdm_device_name
   - source_type: bdm_source_type
   - destination_type: bdm_destination_type
   - delete_on_termination: bdm_delete_on_termination
   - guest_format: bdm_guest_format
   - boot_index: bdm_boot_index
   - config_drive: config_drive
   - key_name: keypair_name
   - os:scheduler_hints: scheduler_hints
   - OS-DCF:diskConfig: server_disk_config


Response Example
----------------

.. literalinclude:: /../../doc/api_samples/servers/server-create-resp.json
   :language: javascript


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - x-openstack-request-id: request_id
   - server: server
   - adminPass: admin_pass
   - name: server_name
   - security_groups: security_groups
   - id: server_id
   - links: generic_links


List Servers Detailed
=====================

.. rest_method:: GET /v2.1/​{tenant_id}​/servers/detail

The compute provisioning algorithm has an anti-affinity property that
attempts to spread customer VMs across hosts. Under certain
situations, VMs from the same customer might be placed on the same
host. The hostId property shows the host that your server runs on and
can be used to determine this scenario if it is relevant to your
application.

For each server, shows server details including configuration drive,
extended status, and server usage information.

The extended status information appears in the OS-EXT-STS:vm_state,
OS-EXT-STS:power_state, and OS-EXT-STS:task_state attributes.

The server usage information appears in the OS-SRV-USG:launched_at and
OS-SRV-USG:terminated_at attributes.

To hide addresses information for instances in a certain state, set
the osapi_hide_server_address_states configuration option. Set this
option to a valid VM state in the nova.conf configuration file.

HostId is unique per account and is not globally unique.

Normal response codes: 200

Error response codes: computeFault (400, 500, …), serviceUnavailable (503), badRequest (400), unauthorized (401), forbidden (403), badMethod (405)

Request Parameters
------------------

.. rest_parameters:: parameters.yaml

   - tenant_id: tenant_id
   - changes-since: changes-since
   - image: image
   - flavor: flavor
   - name: name
   - status: status
   - host: host
   - limit: limit
   - marker: marker


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - servers: servers
   - addresses: server_addresses
   - created: created
   - flavor: flavor_obj
   - hostId: hostId
   - id: server_id
   - image: image_obj
   - key_name: keypair_name
   - links: generic_links
   - metadata: metadata
   - name: server_name
   - OS-DCF:diskConfig: server_disk_config
   - OS-EXT-AZ:availability_zone: availability_zone
   - OS-EXT-SRV-ATTR:host: server_compute_hostname
   - OS-EXT-SRV-ATTR:hypervisor_hostname: server_hypervisor_hostname
   - OS-EXT-SRV-ATTR:instance_name: server_instance_name
   - OS-EXT-STS:power_state: server_power_state
   - OS-EXT-STS:task_state: server_task_state
   - OS-EXT-STS:vm_state: server_vm_state
   - os-extended-volumes:volumes_attached: server_volumes_attached
   - OS-SRV-USG:launched_at: server_launched_at
   - OS-SRV-USG:terminated_at: server_terminated_at
   - progress: build_progress
   - security_groups: security_groups_obj
   - description: sg_description
   - id: sg_id
   - name: sg_name
   - rules: sg_rules
   - status: server_status
   - tenant_id: tenant_id_body
   - updated: updated
   - user_id: user_id
   - locked: server_locked
   - host_status: host_status
   - description: server_description

Example Response
----------------

.. literalinclude:: /../../doc/api_samples/servers/servers-details-resp.json
   :language: javascript

Show Server Details
===================

.. rest_method:: GET /v2.1/​{tenant_id}​/servers/{server_id}

Includes server details including configuration drive, extended
status, and server usage information.

The extended status information appears in the ``OS-EXT-STS:vm_state``,
``OS-EXT-STS:power_state``, and ``OS-EXT-STS:task_state`` attributes.

The server usage information appears in the ``OS-SRV-USG:launched_at``
and ``OS-SRV-USG:terminated_at`` attributes.

To hide addresses information for instances in a certain state, set
the osapi_hide_server_address_states configuration option. Set this
option to a valid VM state in the nova.conf configuration file.

HostId is unique per account and is not globally unique.

Preconditions
-------------

The server must exist.

Normal response codes: 200

Error response codes: computeFault (400, 500, …), serviceUnavailable
(503), badRequest (400), unauthorized (401), forbidden (403),
badMethod (405), itemNotFound (404)


Request Parameters
------------------

.. rest_parameters:: parameters.yaml

  - tenant_id: tenant_id
  - server_id: server_id_url

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - servers: servers
   - addresses: server_addresses
   - created: created
   - flavor: flavor_obj
   - hostId: hostId
   - id: server_id
   - image: image_obj
   - key_name: keypair_name
   - links: generic_links
   - metadata: metadata
   - name: server_name
   - OS-DCF:diskConfig: server_disk_config
   - OS-EXT-AZ:availability_zone: availability_zone
   - OS-EXT-SRV-ATTR:host: server_compute_hostname
   - OS-EXT-SRV-ATTR:hypervisor_hostname: server_hypervisor_hostname
   - OS-EXT-SRV-ATTR:instance_name: server_instance_name
   - OS-EXT-STS:power_state: server_power_state
   - OS-EXT-STS:task_state: server_task_state
   - OS-EXT-STS:vm_state: server_vm_state
   - os-extended-volumes:volumes_attached: server_volumes_attached
   - OS-SRV-USG:launched_at: server_launched_at
   - OS-SRV-USG:terminated_at: server_terminated_at
   - progress: build_progress
   - security_groups: security_groups_obj
   - description: sg_description
   - id: sg_id
   - name: sg_name
   - rules: sg_rules
   - status: server_status
   - tenant_id: tenant_id_body
   - updated: updated
   - user_id: user_id
   - locked: server_locked
   - host_status: host_status
   - description: server_description


Example Response
----------------

.. literalinclude:: /../../doc/api_samples/servers/server-get-resp.json
   :language: javascript


Update Server
=============

.. rest_method:: PUT /v2.1/​{tenant_id}​/servers/​{server_id}

Preconditions
-------------

The server must exist.

You can edit the accessIPv4, accessIPv6, diskConfig and name attributes.

Normal response codes: 200
Error response codes: computeFault (400, 500, …), serviceUnavailable (503), badRequest (400), unauthorized (401), forbidden (403), badMethod (405), itemNotFound (404), buildInProgress (409)

Request Parameters
------------------

(NOTE: sdague) - the upstream docs here are completely scatted and
seem to include the create parameters in this list when most of them
don't work.


.. rest_parameters:: parameters.yaml

  - tenant_id: tenant_id
  - server_id: server_id_url
  - description: server_description


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - servers: servers
   - addresses: server_addresses
   - created: created
   - flavor: flavor_obj
   - hostId: hostId
   - id: server_id
   - image: image_obj
   - key_name: keypair_name
   - links: generic_links
   - metadata: metadata
   - name: server_name
   - OS-DCF:diskConfig: server_disk_config
   - OS-EXT-AZ:availability_zone: availability_zone
   - OS-EXT-SRV-ATTR:host: server_compute_hostname
   - OS-EXT-SRV-ATTR:hypervisor_hostname: server_hypervisor_hostname
   - OS-EXT-SRV-ATTR:instance_name: server_instance_name
   - OS-EXT-STS:power_state: server_power_state
   - OS-EXT-STS:task_state: server_task_state
   - OS-EXT-STS:vm_state: server_vm_state
   - os-extended-volumes:volumes_attached: server_volumes_attached
   - OS-SRV-USG:launched_at: server_launched_at
   - OS-SRV-USG:terminated_at: server_terminated_at
   - progress: build_progress
   - security_groups: security_groups_obj
   - description: sg_description
   - id: sg_id
   - name: sg_name
   - rules: sg_rules
   - status: server_status
   - tenant_id: tenant_id_body
   - updated: updated
   - user_id: user_id
   - locked: server_locked
   - host_status: host_status
   - description: server_description

Example Requests
----------------

Updating the allowed fields for a server

.. literalinclude:: /../../doc/api_samples/servers/server-update-req.json
   :language: javascript


Example Response
----------------

.. literalinclude:: /../../doc/api_samples/servers/server-update-resp.json
   :language: javascript

Delete Server
=============

.. rest_method:: DELETE /v2.1/​{tenant_id}​/servers/​{server_id}

Preconditions
-------------

- The server must exist.
- Anyone can delete a server when the status of the server is not
  locked and when the policy allows.
- If the server is locked, you must have administrator privileges to
  delete the server.

Asynchronous postconditions
---------------------------

- With correct permissions, you can see the server status as DELETED
  through API calls.
- The port attached to the server is deleted.
- The server does not appear in the list servers response.
- The server managed by OpenStack Compute is deleted on the compute
  node.

Troubleshooting
---------------

- If server status remains in deleting status or another error status,
  the request failed. Ensure that you meet the preconditions. Then,
  investigate the compute back end.
- The request returns the HTTP 409 response code when the server is
  locked even if you have correct permissions. Ensure that you meet
  the preconditions then investigate the server status.
- The server managed by OpenStack Compute is not deleted from the
  compute node.

Normal response codes: 204
Error response codes: computeFault (400, 500, …), serviceUnavailable (503), badRequest (400), unauthorized (401), forbidden (403), badMethod (405), itemNotFound (404)

Request Parameters
------------------

.. rest_parameters:: parameters.yaml

  - tenant_id: tenant_id
  - server_id: server_id_url
