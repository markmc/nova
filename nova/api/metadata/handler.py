# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

"""Metadata request handler."""

import base64

import webob.dec
import webob.exc

from nova import compute
from nova import context
from nova import db
from nova import exception
from nova import flags
from nova import log as logging
from nova import network
from nova import volume
from nova import wsgi
from nova.api.ec2 import cloud
from nova.api.ec2 import ec2utils


LOG = logging.getLogger('nova.api.metadata')
FLAGS = flags.FLAGS
flags.DECLARE('use_forwarded_for', 'nova.api.auth')


class Versions(wsgi.Application):

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        """Respond to a request for all versions."""
        # available api versions
        versions = [
            '1.0',
            '2007-01-19',
            '2007-03-01',
            '2007-08-29',
            '2007-10-10',
            '2007-12-15',
            '2008-02-01',
            '2008-09-01',
            '2009-04-04',
            '2011-01-01',
        ]
        return ''.join('%s\n' % v for v in versions)


class MetadataRequestHandler(wsgi.Application):
    """Serve metadata."""

    def __init__(self):
        self.cc = cloud.CloudController()
        self.compute_api = compute.API(
                network_api=network.API(),
                volume_api=volume.API())

    def get_metadata(self, address):
        ctxt = context.get_admin_context()
        search_opts = {'fixed_ip': address, 'deleted': False}
        try:
            instance_ref = self.compute_api.get_all(ctxt,
                    search_opts=search_opts)
        except exception.NotFound:
            instance_ref = None
        if not instance_ref:
            return None

        # This ensures that all attributes of the instance
        # are populated.
        instance_ref = db.instance_get(ctxt, instance_ref[0]['id'])

        mpi = self.cc._get_mpi_data(ctxt, instance_ref['project_id'])
        hostname = "%s.%s" % (instance_ref['hostname'], FLAGS.dhcp_domain)
        host = instance_ref['host']
        services = db.service_get_all_by_host(ctxt.elevated(), host)
        availability_zone = ec2utils.get_availability_zone_by_host(services,
                                                                   host)

        ip_info = ec2utils.get_ip_info_for_instance(ctxt, instance_ref)
        floating_ips = ip_info['floating_ips']
        floating_ip = floating_ips and floating_ips[0] or ''

        ec2_id = ec2utils.id_to_ec2_id(instance_ref['id'])
        image_ec2_id = ec2utils.image_ec2_id(instance_ref['image_ref'])
        security_groups = db.security_group_get_by_instance(ctxt,
                                                            instance_ref['id'])
        security_groups = [x['name'] for x in security_groups]
        mappings = self.cc._format_instance_mapping(ctxt, instance_ref)
        data = {
            'user-data': base64.b64decode(instance_ref['user_data']),
            'meta-data': {
                'ami-id': image_ec2_id,
                'ami-launch-index': instance_ref['launch_index'],
                'ami-manifest-path': 'FIXME',
                'block-device-mapping': mappings,
                'hostname': hostname,
                'instance-action': 'none',
                'instance-id': ec2_id,
                'instance-type': instance_ref['instance_type']['name'],
                'local-hostname': hostname,
                'local-ipv4': address,
                'placement': {'availability-zone': availability_zone},
                'public-hostname': hostname,
                'public-ipv4': floating_ip,
                'reservation-id': instance_ref['reservation_id'],
                'security-groups': security_groups,
                'mpi': mpi}}

        # public-keys should be in meta-data only if user specified one
        if instance_ref['key_name']:
            data['meta-data']['public-keys'] = {
                '0': {'_name': instance_ref['key_name'],
                      'openssh-key': instance_ref['key_data']}}

        for image_type in ['kernel', 'ramdisk']:
            if instance_ref.get('%s_id' % image_type):
                ec2_id = ec2utils.image_ec2_id(
                        instance_ref['%s_id' % image_type],
                        self._image_type(image_type))
                data['meta-data']['%s-id' % image_type] = ec2_id

        if False:  # TODO(vish): store ancestor ids
            data['ancestor-ami-ids'] = []
        if False:  # TODO(vish): store product codes
            data['product-codes'] = []
        return data

    def print_data(self, data):
        if isinstance(data, dict):
            output = ''
            for key in data:
                if key == '_name':
                    continue
                output += key
                if isinstance(data[key], dict):
                    if '_name' in data[key]:
                        output += '=' + str(data[key]['_name'])
                    else:
                        output += '/'
                output += '\n'
            # Cut off last \n
            return output[:-1]
        elif isinstance(data, list):
            return '\n'.join(data)
        else:
            return str(data)

    def lookup(self, path, data):
        items = path.split('/')
        for item in items:
            if item:
                if not isinstance(data, dict):
                    return data
                if not item in data:
                    return None
                data = data[item]
        return data

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        remote_address = req.remote_addr
        if FLAGS.use_forwarded_for:
            remote_address = req.headers.get('X-Forwarded-For', remote_address)
        try:
            meta_data = self.get_metadata(remote_address)
        except Exception:
            LOG.exception(_('Failed to get metadata for ip: %s'),
                          remote_address)
            msg = _('An unknown error has occurred. '
                    'Please try your request again.')
            exc = webob.exc.HTTPInternalServerError(explanation=unicode(msg))
            return exc
        if meta_data is None:
            LOG.error(_('Failed to get metadata for ip: %s'), remote_address)
            raise webob.exc.HTTPNotFound()
        data = self.lookup(req.path_info, meta_data)
        if data is None:
            raise webob.exc.HTTPNotFound()
        return self.print_data(data)
