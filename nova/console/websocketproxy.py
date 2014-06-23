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

'''
Websocket proxy that is compatible with OpenStack Nova.
Leverages websockify.py by Joel Martin
'''

import Cookie
import os
import socket

from oslo.config import cfg
import websockify

from nova.consoleauth import rpcapi as consoleauth_rpcapi
from nova import context
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)

websocketproxy_opts = [
    cfg.BoolOpt('record',
                default=False,
                help='Record sessions to FILE.[session_number]'),
    cfg.BoolOpt('daemon',
                default=False,
                help='Become a daemon (background process)'),
    cfg.BoolOpt('ssl_only',
                default=False,
                help='Disallow non-encrypted connections'),
    cfg.BoolOpt('source_is_ipv6',
                default=False,
                help='Source is ipv6'),
    cfg.StrOpt('cert',
               default='self.pem',
               help='SSL certificate file'),
    cfg.StrOpt('key',
               help='SSL key file (if separate from cert)'),
    cfg.StrOpt('web',
               help='Run webserver on same port. Serve files from DIR.'),
    ]

novnc_opts = [
    cfg.StrOpt('novncproxy_host',
               default='0.0.0.0',
               help='Host on which to listen for incoming requests'),
    cfg.IntOpt('novncproxy_port',
               default=6080,
               help='Port on which to listen for incoming requests'),
    ]

spice_opts = [
    cfg.StrOpt('html5proxy_host',
               default='0.0.0.0',
               help='Host on which to listen for incoming requests',
               deprecated_group='DEFAULT',
               deprecated_name='spicehtml5proxy_host'),
    cfg.IntOpt('html5proxy_port',
               default=6082,
               help='Port on which to listen for incoming requests',
               deprecated_group='DEFAULT',
               deprecated_name='spicehtml5proxy_port'),
    ]

CONF = cfg.CONF
CONF.register_cli_opts(websocketproxy_opts)
CONF.register_cli_opts(novnc_opts)
CONF.register_cli_opts(spice_opts, group='spice')


class InvalidWebSocketProxyConfig(Exception):
    pass


def set_defaults(web):
    cfg.set_defaults(websocketproxy_opts, web=web)


def create(listen_host, listen_port, file_only=False):
    if CONF.ssl_only and not os.path.exists(CONF.cert):
        raise InvalidWebSocketProxyConfig(
            _("SSL only and %s not found.") % CONF.cert)

    if not os.path.exists(CONF.web):
        raise InvalidWebSocketProxyConfig(
            _("Can not find html/js/css files at %s.") % CONF.web)

    return NovaWebSocketProxy(listen_host=listen_host,
                              listen_port=listen_port,
                              source_is_ipv6=CONF.source_is_ipv6,
                              verbose=CONF.verbose,
                              cert=CONF.cert,
                              key=CONF.key,
                              ssl_only=CONF.ssl_only,
                              daemon=CONF.daemon,
                              record=CONF.record,
                              traffic=CONF.verbose and not CONF.daemon,
                              web=CONF.web,
                              file_only=file_only,
                              RequestHandlerClass=NovaProxyRequestHandler)


def create_spice_html5proxy(conf):
    return create(conf,
                  CONF.spice.html5proxy_host,
                  CONF.spice.html5proxy_port)


def create_novnc_proxy(conf):
    return create(conf,
                  CONF.novncproxy_host,
                  CONF.novncproxy_port)


class NovaProxyRequestHandlerBase(object):
    def new_websocket_client(self):
        """Called after a new WebSocket connection has been established."""
        # Reopen the eventlet hub to make sure we don't share an epoll
        # fd with parent and/or siblings, which would be bad
        from eventlet import hubs
        hubs.use_hub()

        cookie = Cookie.SimpleCookie()
        cookie.load(self.headers.getheader('cookie'))
        token = cookie['token'].value
        ctxt = context.get_admin_context()
        rpcapi = consoleauth_rpcapi.ConsoleAuthAPI()
        connect_info = rpcapi.check_token(ctxt, token=token)

        if not connect_info:
            raise Exception(_("Invalid Token"))

        self.msg(_('connect info: %s'), str(connect_info))
        host = connect_info['host']
        port = int(connect_info['port'])

        # Connect to the target
        self.msg(_("connecting to: %(host)s:%(port)s") % {'host': host,
                                                          'port': port})
        tsock = self.socket(host, port, connect=True)

        # Handshake as necessary
        if connect_info.get('internal_access_path'):
            tsock.send("CONNECT %s HTTP/1.1\r\n\r\n" %
                        connect_info['internal_access_path'])
            while True:
                data = tsock.recv(4096, socket.MSG_PEEK)
                if data.find("\r\n\r\n") != -1:
                    if not data.split("\r\n")[0].find("200"):
                        raise Exception(_("Invalid Connection Info"))
                    tsock.recv(len(data))
                    break

        # Start proxying
        try:
            self.do_proxy(tsock)
        except Exception:
            if tsock:
                tsock.shutdown(socket.SHUT_RDWR)
                tsock.close()
                self.vmsg(_("%(host)s:%(port)s: Target closed") %
                          {'host': host, 'port': port})
            raise


# TODO(sross): when the websockify version is bumped to be >=0.6,
#              remove the if-else statement and make the if branch
#              contents the only code.
if getattr(websockify, 'ProxyRequestHandler', None) is not None:
    class NovaProxyRequestHandler(NovaProxyRequestHandlerBase,
                                  websockify.ProxyRequestHandler):
        def __init__(self, *args, **kwargs):
            websockify.ProxyRequestHandler.__init__(self, *args, **kwargs)

        def socket(self, *args, **kwargs):
            return websockify.WebSocketServer.socket(*args, **kwargs)

    class NovaWebSocketProxy(websockify.WebSocketProxy):
        @staticmethod
        def get_logger():
            return LOG

else:
    import sys

    class NovaWebSocketProxy(NovaProxyRequestHandlerBase,
                             websockify.WebSocketProxy):
        def __init__(self, *args, **kwargs):
            del kwargs['traffic']
            del kwargs['RequestHandlerClass']
            websockify.WebSocketProxy.__init__(self, *args,
                                               target_host='ignore',
                                               target_port='ignore',
                                               unix_target=None,
                                               target_cfg=None,
                                               ssl_target=None,
                                               **kwargs)

        def new_client(self):
            self.new_websocket_client()

        def msg(self, *args, **kwargs):
            LOG.info(*args, **kwargs)

        def vmsg(self, *args, **kwargs):
            LOG.debug(*args, **kwargs)

        def warn(self, *args, **kwargs):
            LOG.warn(*args, **kwargs)

        def print_traffic(self, token="."):
            if self.traffic:
                sys.stdout.write(token)
                sys.stdout.flush()

    class NovaProxyRequestHandler(object):
        pass
