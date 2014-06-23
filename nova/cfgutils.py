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

import os
import pkgutil
import sys

from oslo.config import cfg


def iter_opts(obj):
    def is_opt(o):
        return (isinstance(o, cfg.Opt) and
                not isinstance(o, cfg.SubCommandOpt))

    for attr_str in dir(obj):
        attr_obj = getattr(obj, attr_str)
        if is_opt(attr_obj):
            yield attr_obj
        elif isinstance(attr_obj, list):
            for opt in attr_obj:
                if is_opt(opt):
                    yield opt


def walk_opts(top, excludes=None):
    excludes = excludes or []

    def iter_module_opts(mod):
        if mod not in excludes:
            __import__(mod)
            for opt in iter_opts(sys.modules[mod]):
                yield mod, opt

    for mod, opt in iter_module_opts(top):
        yield mod, opt

    path = top.replace('.', os.sep)
    for importer, name, ispkg in pkgutil.walk_packages([path], top + '.'):
        for mod, opt in iter_module_opts(name):
            yield mod, opt


def list_opts(top, excludes=None):
    return [o for m, o in walk_opts(top, excludes)]
