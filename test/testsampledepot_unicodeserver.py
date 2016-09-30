#!/usr/bin/env python

import os

from replicationunittest import ReplicationTestCaseWithDocker
from testcommon import get_p4d_from_docker, set_p4d_unicode_mode, replicate_sample_view
from lib.buildlogger import getLogger
from lib.buildcommon import generate_random_str

import tempfile
import testsampledepot
import testsampledepot_misc

logger = getLogger(__name__)

class P4P4ReplicationTestUnicodeServer(ReplicationTestCaseWithDocker):
    def replicate_sample_dir_withdocker_unicodeserver(self, depot_dir, **kwargs):
        '''replicate depot_dir to svn

        @param depot_dir, e.g. /depot/Jam
        '''
        src_depot = '/%s/...' % depot_dir
        dst_depot = '//depot/buildtest%s/...' % depot_dir

        src_view = ((src_depot, './...'),)
        dst_view = ((dst_depot, './...'),)

        src_docker = kwargs.pop('src_docker_cli', None)
        if not src_docker:
            src_docker = self.docker_clients[0]

        dst_docker = kwargs.pop('dst_docker_cli', None)
        if not dst_docker:
            dst_docker = self.docker_clients[1]

        if kwargs.pop('src_unicode_server', None):
            set_p4d_unicode_mode(src_docker)
        if kwargs.pop('dst_unicode_server', None):
            set_p4d_unicode_mode(dst_docker)

        replicate_sample_view(src_view, dst_view,
                              src_docker_cli=src_docker,
                              dst_docker_cli=dst_docker,
                              **kwargs)
        return dst_depot


class SampleDepotTestSourceUnicodeServer(P4P4ReplicationTestUnicodeServer,
                                         testsampledepot_misc.SampleDepotTestMisc):
    @classmethod
    def setUpClass(cls):
        super(SampleDepotTestSourceUnicodeServer, cls).setUpClass()
        set_p4d_unicode_mode(cls.docker_clients[0])

    def replicate_sample_dir_withdocker(self, depot_dir, **kwargs):
        return self.replicate_sample_dir_withdocker_unicodeserver(depot_dir,
                                                           src_unicode_server=True,
                                                           **kwargs)

    def test_replicate_sample_commit_message_reformat_review(self):
        pass

class SampleDepotTestTargetUnicodeServer(P4P4ReplicationTestUnicodeServer,
                                         testsampledepot_misc.SampleDepotTestMisc):
    @classmethod
    def setUpClass(cls):
        super(SampleDepotTestTargetUnicodeServer, cls).setUpClass()
        set_p4d_unicode_mode(cls.docker_clients[1])

    def replicate_sample_dir_withdocker(self, depot_dir, **kwargs):
        return self.replicate_sample_dir_withdocker_unicodeserver(depot_dir,
                                                           dst_unicode_server=True,
                                                           **kwargs)

    def test_replicate_sample_commit_message_reformat_review(self):
        pass


class SampleDepotTestBothUnicodeServer(P4P4ReplicationTestUnicodeServer,
                                       testsampledepot_misc.SampleDepotTestMisc):
    @classmethod
    def setUpClass(cls):
        super(SampleDepotTestBothUnicodeServer, cls).setUpClass()
        set_p4d_unicode_mode(cls.docker_clients[2])
        set_p4d_unicode_mode(cls.docker_clients[1])

    def replicate_sample_dir_withdocker(self, depot_dir, **kwargs):
        return self.replicate_sample_dir_withdocker_unicodeserver(depot_dir,
                                                           src_unicode_server=True,
                                                           dst_unicode_server=True,
                                                           **kwargs)

    def test_replicate_sample_commit_message_reformat_review(self):
        pass

    
if __name__ == '__main__':
    import unittest
    unittest.main()
