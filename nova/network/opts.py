# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import itertools

import nova.network
import nova.network.driver
import nova.network.floating_ips
import nova.network.rpcapi
import nova.network.security_group.openstack_driver


def list_opts():
    return [
        ('DEFAULT',
         itertools.chain(
             nova.network._network_opts,
             nova.network.driver.driver_opts,
             nova.network.rpcapi.rpcapi_opts,
             nova.network.security_group.openstack_driver.security_group_opts,
         ))
    ]
