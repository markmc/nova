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

import collections
import itertools
import operator
import os.path
import re

import fixtures
from oslo.config import cfg

from nova import cfgutils
from nova import utils


class ConfigGeneratorTestCase(object):

    namespaces = None
    filename = None
    top_module = None
    excludes = None

    def setUp(self):
        super(ConfigGeneratorTestCase, self).setUp()

        if any([i is None for i in (self.namespaces,
                                    self.filename,
                                    self.top_module,
                                    self.excludes)]):
            raise ValueError('Incorrectly subclassed config generator test')

        self._temp_dir = self.useFixture(fixtures.TempDir())

        self._key_re = re.compile('#([^ =]+) =')
        self._help_re = re.compile('# (.*)')

    def _read_opts_from_sample(self, path):
        with open(path) as f:
            contents = f.readlines()

        help_str = None
        opts = collections.defaultdict(list)
        for line in contents:
            line = line.strip()
            if not line:
                help_str = None
                continue

            if help_str is None:
                m = self._help_re.match(line)
                if m is not None:
                    help_str = m.group(1)

            m = self._key_re.match(line)
            if m is not None:
                opt = cfg.Opt(m.group(1), help=help_str)
                help_str = None
                opts[opt.dest].append(opt)

        return contents, opts

    def test_config_generator(self):
        sample_file = os.path.join(self._temp_dir.path, self.filename)
        self.assertFalse(os.path.exists(sample_file))

        args = ['oslo-config-generator']
        args.extend(['--namespace=' + n for n in self.namespaces])
        args.append('--output-file=' + sample_file)

        utils.execute(*args)
        self.assertTrue(os.path.exists(sample_file))

        sample_contents, sample_opts = self._read_opts_from_sample(sample_file)

        discovered_opts = cfgutils.walk_opts(self.top_module, self.excludes)

        def opt_looks_like(real, sample):
            return (real.dest == sample.dest and
                    (real.help.startswith(sample.help) or
                     sample.help.startswith(real.help)))

        seen = set()
        for mod, discovered_opt in discovered_opts:
            if discovered_opt in seen:
                continue
            seen.add(discovered_opt)

            for sample_opt in sample_opts[discovered_opt.dest]:
                if opt_looks_like(discovered_opt, sample_opt):
                    sample_opts[discovered_opt.dest].remove(sample_opt)
                    break
            else:
                candidates = [o.help for o in sample_opts[discovered_opt.dest]]
                candidates = candidates or ['(none)']
                raise AssertionError('Discovered option "%(opt)s" with help '
                                     '"%(help)s" from %(mod)s not found in '
                                     'sample. \nCandidate help strings:\n'
                                     '  %(candidates)s\n\nFull sample:\n'
                                     '  %(sample)s' %
                                     {'opt': discovered_opt.dest,
                                      'help': discovered_opt.help,
                                      'mod': mod,
                                      'candidates': '\n  '.join(candidates),
                                      'sample': '  '.join(sample_contents)})

        if any(sample_opts.values()):
            leftovers = itertools.chain(*sample_opts.values())
            leftovers = sorted(leftovers, key=operator.attrgetter('dest'))
            raise AssertionError('Values in sample not found in code:\n  ' +
                                 ('\n  '.join(['%s: %s' % (o.dest, o.help)
                                               for o in leftovers])))
