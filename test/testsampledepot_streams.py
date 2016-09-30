#!/usr/bin/env python

'''test replication of streams in perforce sampledepot.

'''
import unittest

from testcommon import replicate_sample_view
from lib.buildlogger import getLogger
from replicationunittest import ReplicationTestCaseWithDocker

logger = getLogger(__name__)


class SampleDepotTestStream(ReplicationTestCaseWithDocker):

    def replicate_sample_dir_withdocker(self, depot_dir, **kwargs):
        '''test replicating directory

        create/start src/dst docker containers.  connect to src/dst
        p4d
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

        replicate_sample_view(src_view, dst_view,
                              src_docker_cli=src_docker,
                              dst_docker_cli=dst_docker,
                              **kwargs)
        return dst_depot


    def test_replicate_sample_streams_gwt_streams(self):
        ''''//gwt-streams/...'
        '''
        stream_dirs = ['/gwt-streams/experimental',
                       '/gwt-streams/earl-dev',
                       '/gwt-streams/main',
                       '/gwt-streams/release1.5',
                       '/gwt-streams/release2.0',]

        for depot_dir in stream_dirs:
            self.replicate_sample_dir_withdocker(depot_dir,
                                                 source_p4_stream='/'+depot_dir)



    def test_replicate_sample_streams_jam(self):
        ''' //jam/...
        '''
        stream_dirs = ['/jam/main',
                       '/jam/dev2.3',
                       '/jam/rel2.1',
                       '/jam/rel2.2',
                       '/jam/rel2.3',]

        for depot_dir in stream_dirs:
            stream = '/' + depot_dir
            self.replicate_sample_dir_withdocker(depot_dir,
                                                 source_p4_stream=stream)


    def test_replicate_sample_streams_pb(self):
        ''' //pb/...
        '''
        stream_dirs = [
            '/pb/1.0-r',
            '/pb/1.5-r',
            '/pb/1.5.1-p',
            '/pb/2.0-int',
            '/pb/dev-db',
            '/pb/dev-db-linux',
            '/pb/dev-gui',
            '/pb/dev1.0',
            '/pb/main', ]

        for depot_dir in stream_dirs:
            stream = '/' + depot_dir
            self.replicate_sample_dir_withdocker(depot_dir,
                                                 source_p4_stream=stream)



if __name__ == '__main__':
    unittest.main()

