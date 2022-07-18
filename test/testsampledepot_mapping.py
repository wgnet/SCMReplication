#!/usr/bin/python3

'''test replication of depots in perforce sampledepot with complex
mappings.

test cases includes:
 - replicate files from multiple directories
 - replicate files and reorganize directories in target depot
 - exclude certain file types   '-//depot/James/....exe'
 - exclude some directories
 - replicate files of same 'label', not required
'''

from testcommon import (replicate_sample_view, )
from lib.buildlogger import getLogger
from replicationunittest import ReplicationTestCaseWithDocker

logger = getLogger(__name__)


class SampleDepotMappingTest(ReplicationTestCaseWithDocker):

    def replicate_sample_view_with_docker(self, src_view, dst_view, **kwargs):
        replicate_sample_view(src_view, dst_view,
                              self.docker_clients[0],
                              self.docker_clients[1], **kwargs)

    def test_replicate_sample_depot_onedir_mapping(self):
        test_case = 'replicate_sample_depot_onedir_mapping'

        src_view = (('//depot/www/...', './www/...'),)
        dst_view = (('//depot/buildtest/...', './...'),)
        self.replicate_sample_view_with_docker(src_view, dst_view)

        logger.passed(test_case)

    def test_replicate_sample_depot_twodir_mapping(self):
        test_case = 'replicate_sample_depot_twodir_mapping'

        src_view = (('//depot/Jam/...', './Jam-rep/...'),
                    ('//depot/Talkhouse/...', './Talkhouse-rep/...'),)
        dst_view = (('//depot/buildtest0/Jam/...', './Jam-rep/...'),
                    ('//depot/buildtest1/Talkhouse/...', './Talkhouse-rep/...'),)

        self.replicate_sample_view_with_docker(src_view, dst_view)

        logger.passed(test_case)

    def test_replicate_sample_depot_reorg_mapping(self):
        test_case = 'replicate_sample_depot_reorg_mapping'

        src_view = (('//depot/Jam/MAIN/...', './Jam_MAIN/...'),
                    ('//depot/Misc/manuals/...', './Misc_manuals/...'),
                    ('//depot/www/live/...', './www_live/...'),)
        dst_view = (('//depot/buildtest/mixture/...', './...'),)

        self.replicate_sample_view_with_docker(src_view, dst_view)

        logger.passed(test_case)

    def test_replicate_sample_depot_excludedir_mapping(self):
        test_case = 'replicate_sample_depot_excludedir_mapping'

        src_view = (('//depot/Jam/...', './...'),
                    ('-//depot/Jam/REL2.1/...', './REL2.1/...'),)
        dst_view = (('//depot/buildtest/Jam/...', './...'),)

        self.replicate_sample_view_with_docker(src_view, dst_view)

        logger.passed(test_case)

    def test_replicate_sample_depot_overlay_mapping(self):
        test_case = 'replicate_sample_depot_overlay_mapping'

        src_view = (('//depot/www/...', './...'),
                    ('+//depot/Talkhouse/rel1.0/...', './...'),)
        dst_view = (('//depot/buildtest/...', './...'),)

        self.replicate_sample_view_with_docker(
            src_view, dst_view, skip_verification=True)

        logger.passed(test_case)


if __name__ == '__main__':
    import unittest
    unittest.main()
