# Copyright (c) 2012 OpenStack Foundation
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

"""
Websocket proxy that is compatible with OpenStack Nova
SPICE HTML5 consoles. Leverages websockify.py by Joel Martin
"""

from __future__ import print_function

import sys

from oslo.config import cfg

from nova import config
from nova.console import websocketproxy
from nova.openstack.common import log as logging
from nova.openstack.common.report import guru_meditation_report as gmr
from nova import version


def main():
    websocketproxy.set_defaults(web='/usr/share/spice-html5')
    config.parse_args(sys.argv)

    logging.setup("nova")

    gmr.TextGuruMeditation.setup_autorun(version)

    try:
        server = websocketproxy.create_spice_html5proxy(cfg.CONF)
    except websocketproxy.InvalidWebSocketProxyConfig as ex:
        print(str(ex))
        return -1

    server.start_server()
