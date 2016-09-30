#!/usr/bin/env python

'''test replication of depots in perforce sampledepot.

Structure of the Sample Depot
    Stream-based Software Development Projects
        //jam
        //pb
        //gwt-streams
    Software Development Projects
        //depot/Jam (retired)
        //depot/Jamgraph
        //depot/Talkhouse
        //gwt
    Web Site Development
        //depot/www
    Stream-based Document Management
        //HR
    Miscellaneous Shared Files
        //depot/Misc
 
Software Development Branching Methodology
Ongoing development work occurs in the MAIN or trunk branch under each
software project's name.  Branches might be created for feature
development. Such branches isolate development work that might
destabilize the MAIN branch.  When code is ready for release, a
release branch is created under the project name.

Web Site Branching Methodology
    Web page authors edit files under:
        //depot/www/dev
    Files are copied to a staging area for final review before going live:
        //depot/www/review
    After passing review, files are copied to a live branch for publishing:
        //depot/www/live
'''
import unittest

from testcommon import replicate_sample_dir
from lib.buildlogger import getLogger
from replicationunittest import ReplicationTestCaseWithDocker

logger = getLogger(__name__)


class SampleDepotTest(ReplicationTestCaseWithDocker):

    def replicate_sample_dir_withdocker(self, depot_dir):
        replicate_sample_dir(depot_dir,
                             src_docker_cli=self.docker_clients[0],
                             dst_docker_cli=self.docker_clients[1])

    def test_replicate_sample_depot_Jam(self):
        '''''//depot/Jam/...': set(['add', 'branch', 'delete', 'edit',
                                    'integrate'])
        '''
        test_case = 'replicate_sample_depot_Jam'

        depot_dir = '/depot/Jam'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_depot_Jamgraph(self):
        ''''//depot/Jamgraph/...': set(['add', 'branch', 'delete',
                                        'edit', 'integrate'])

        file types:
            binary files, .dll, .exe
            image files, .gif
        '''
        test_case = 'replicate_sample_depot_Jamgraph'

        depot_dir = '/depot/Jamgraph'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_depot_Misc(self):
        ''''//depot/Misc/...': set(['add', 'edit'])

        file types:
            doc files: .doc/.xls
            photoshop document files: .psd
            maya binary file: .mb
        '''
        test_case = 'replicate_sample_depot_Misc'

        depot_dir = '/depot/Misc'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_depot_perfmerge(self):
        ''''//depot/perfmerge/...': set(['add']),
        '''
        test_case = 'replicate_sample_depot_perfmerge'

        depot_dir = '/depot/perfmerge'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_depot_Talkhouse(self):
        ''''//depot/Talkhouse/...': set(['add', 'branch', 'delete', 'edit',
        'integrate'])

        file types:
            binary: .jar
        '''
        test_case = 'replicate_sample_depot_Talkhouse'

        depot_dir = '/depot/Talkhouse'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_HR(self):
        ''''//HR/...': set(['add', 'branch', 'edit', 'integrate'])

        file types:
            .rtf files
        '''
        test_case = 'replicate_sample_HR'

        depot_dir = '/HR'
        self.replicate_sample_dir_withdocker(depot_dir)        

        logger.passed(test_case)

    def test_replicate_sample_depot_www(self):
        ''''//depot/www/...': set(['add', 'branch', 'edit', 'integrate'])
        '''
        test_case = 'replicate_sample_depot_www'

        depot_dir = '/depot/www'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_gwt(self):
        ''''//gwt/...': set(['add', 'branch', 'delete', 'edit'])
        '''
        test_case = 'replicate_sample_gwt'

        depot_dir = '/gwt'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    @unittest.skip('there are errors in history of //pb/dev-gui/gui/tabs.xml')
    def test_replicate_sample_pb(self):
        '''testing replication of //pb

        Integration source file //pb/main/src/make.c#2 is
        older than target file //depot/buildtest/pb/main/src/make.c#1.
        Cannot progress.

        there seems to be some errors in the sample depot, check
        //pb/dev-gui/gui/tabs.xml
        '''
        test_case = 'replicate_sample_pb'

        depot_dir = '/pb'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_gwt_streams(self):
        ''''//gwt-streams/...': set(['add', 'branch', 'delete', 'edit',
                                     'integrate', 'move/add', 'move/delete']),
        '''
        test_case = 'replicate_sample_gwt_streams'

        depot_dir = '/gwt-streams'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)

    def test_replicate_sample_jam(self):
        ''''//jam/...': set(['branch', 'edit', 'integrate'])
        '''
        test_case = 'replicate_sample_jam'

        depot_dir = '/jam'
        self.replicate_sample_dir_withdocker(depot_dir)

        logger.passed(test_case)


failed_tests = unittest.TestSuite()
failed_tests.addTest(SampleDepotTest('test_replicate_sample_pb'))

if __name__ == '__main__':
    unittest.main()

