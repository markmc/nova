# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright 2014 Red Hat, Inc.
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

import itertools

from oslo.config import cfg

from nova import cfgutils
from nova import debugger
from nova.openstack.common.db import options
from nova import paths
from nova import rpc
from nova import version

_DEFAULT_SQL_CONNECTION = 'sqlite:///' + paths.state_path_def('nova.sqlite')


def parse_args(argv, default_config_files=None):
    options.set_defaults(sql_connection=_DEFAULT_SQL_CONNECTION,
                         sqlite_db='nova.sqlite')
    rpc.set_defaults(control_exchange='nova')
    debugger.register_cli_opts()
    cfg.CONF(argv[1:],
             project='nova',
             version=version.version_string(),
             default_config_files=default_config_files)
    rpc.init(cfg.CONF)


def list_opts():
    import nova.api.openstack
    import nova.baserpc
    import nova.cells.rpc_driver
    import nova.cells.rpcapi
    import nova.cert.rpcapi
    import nova.compute.rpcapi
    import nova.conductor.rpcapi
    import nova.console.rpcapi
    import nova.consoleauth.rpcapi
    import nova.db.api
    import nova.db.base
    import nova.db.sqlalchemy.api
    import nova.image.download.file
    import nova.network.rpcapi
    import nova.scheduler.rpcapi

    global_opts_lists = [
        nova.cert.rpcapi.rpcapi_opts,
        nova.compute.rpcapi.rpcapi_opts,
        nova.console.rpcapi.rpcapi_opts,
        nova.db.api.db_opts,
        [nova.db.base.db_driver_opt],
        nova.db.sqlalchemy.api.db_opts,
        nova.network.rpcapi.rpcapi_opts,
        nova.scheduler.rpcapi.rpcapi_opts,
    ]

    def walk(top, excludes=None):
        global_opts_lists.append(cfgutils.list_opts(top, excludes))

    walk('nova.availability_zones')
    walk('nova.api', excludes=['nova.api.openstack'])
    walk('nova.cloudpipe')
    walk('nova.compute', excludes=['nova.compute.rpcapi'])
    walk('nova.conductor.tasks')
    walk('nova.console', excludes=['nova.console.rpcapi'])
    walk('nova.consoleauth', excludes=['nova.consoleauth.rpcapi'])
    walk('nova.crypto')
    walk('nova.exception')
    walk('nova.image.s3')
    walk('nova.ipv6')
    walk('nova.openstack.common',
         excludes=['nova.openstack.common.db.options',
                   'nova.openstack.common.db.sqlalchemy.test_migrations',
                   'nova.openstack.common.sslutils'])
    walk('nova.netconf')
    walk('nova.network', excludes=['nova.network.rpcapi',
                                   'nova.network.neutronv2.api'])
    walk('nova.notifications')
    walk('nova.objects')
    walk('nova.objectstore')
    walk('nova.paths')
    walk('nova.pci')
    walk('nova.quota')
    walk('nova.scheduler', excludes=['nova.scheduler.rpcapi',
                                     'nova.scheduler.weights.metrics',
                                     'nova.scheduler.filters.trusted_filter'])
    walk('nova.service')
    walk('nova.servicegroup.api')
    walk('nova.utils')
    walk('nova.virt.configdrive')
    walk('nova.virt.disk')
    walk('nova.virt.driver')
    walk('nova.virt.firewall')
    walk('nova.virt.hardware')
    walk('nova.virt.imagecache')
    walk('nova.virt.images')
    walk('nova.vnc')
    walk('nova.volume')
    walk('nova.wsgi')

    rpcapi_cap_opts = [
        nova.baserpc.rpcapi_cap_opt,
        nova.cells.rpc_driver.rpcapi_cap_opt,
        nova.cells.rpcapi.rpcapi_cap_opt,
        nova.cert.rpcapi.rpcapi_cap_opt,
        nova.compute.rpcapi.rpcapi_cap_opt,
        nova.conductor.rpcapi.rpcapi_cap_opt,
        nova.console.rpcapi.rpcapi_cap_opt,
        nova.consoleauth.rpcapi.rpcapi_cap_opt,
        nova.network.rpcapi.rpcapi_cap_opt,
        nova.scheduler.rpcapi.rpcapi_cap_opt,
    ]

    cells_opts_lists = [
        nova.cells.rpc_driver.cell_rpc_driver_opts,
    ]
    cells_opts_lists.append(
        cfgutils.list_opts('nova.cells',
                           excludes=['nova.cells.rpc_driver',
                                     'nova.cells.rpcapi']))

    database_opts_lists = [
        nova.db.api.tpool_opts,
        nova.db.sqlalchemy.api.connection_opts,
        nova.openstack.common.db.options.database_opts,
    ]

    def chain(lists):
        return list(itertools.chain(*lists))

    opts = [
        (None, chain(global_opts_lists)),
        ('baremetal', cfgutils.list_opts('nova.virt.baremetal')),
        ('cells', chain(cells_opts_lists)),
        ('conductor', cfgutils.list_opts('nova.conductor.api')),
        ('database', chain(database_opts_lists)),
        ('glance', cfgutils.list_opts('nova.image.glance')),
        ('hyperv', cfgutils.list_opts('nova.virt.hyperv')),
        ('image_file_url', [nova.image.download.file.opt_group]),
        ('image_file_url:FILESYSTEM_ID',
         nova.image.download.file.filesystem_opts),
        ('key_mgr', cfgutils.list_opts('nova.keymgr')),
        ('libvirt', cfgutils.list_opts('nova.virt.libvirt')),
        ('metrics', cfgutils.list_opts('nova.scheduler.weights.metrics')),
        ('neutron', cfgutils.list_opts('nova.network.neutronv2')),
        ('osapi_v3', nova.api.openstack.api_opts),
        ('rdp', cfgutils.list_opts('nova.rdp')),
        ('spice', cfgutils.list_opts('nova.spice')),
        ('ssl', cfgutils.list_opts('nova.openstack.common.sslutils')),
        ('trusted_computing',
         cfgutils.list_opts('nova.scheduler.filters.trusted_filter')),
        ('upgrade_levels', rpcapi_cap_opts),
        ('vmware', cfgutils.list_opts('nova.virt.vmwareapi')),
        ('xenserver', cfgutils.list_opts('nova.virt.xenapi')),
        ('zookeeper', cfgutils.list_opts('nova.servicegroup.drivers.zk')),
    ]

    return opts
