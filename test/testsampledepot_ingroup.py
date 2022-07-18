#!/usr/bin/python3

'''test replication of perforce sampledepot in group.
'''

from testcommon import replicate_sampledir_in_groups
from lib.buildlogger import getLogger
from replicationunittest import ReplicationTestCaseWithDocker

logger = getLogger(__name__)


class SampleDepotTestGroup(ReplicationTestCaseWithDocker):

    def replicate_sampledir_in_groups_with_docker(self, depot_dir,
                                                  num_changes_per_round,
                                                  **kwargs):
        replicate_sampledir_in_groups(depot_dir,
                                      self.docker_clients[0],
                                      self.docker_clients[1],
                                      self.docker_clients[2],
                                      num_changes_per_round, **kwargs)

    def test_replicate_group_sample_depot_Jam(self):
        test_case = 'replicate_sample_depot_Jam_ingroup'
        depot_dir = '/depot/Jam'
        self.replicate_sampledir_in_groups_with_docker(depot_dir, 10)

        logger.passed(test_case)

    def test_replicate_group_sample_depot_Jamgraph(self):
        test_case = 'replicate_sample_depot_Jamgraph_ingroup'
        depot_dir = '/depot/Jamgraph'
        self.replicate_sampledir_in_groups_with_docker(depot_dir, 1)

        logger.passed(test_case)

    def test_replicate_group_sample_depot_Jamgraph_changing_repinfo_location(
            self):
        test_case = 'replicate_sample_depot_Jamgraph_ingroup'
        depot_dir = '/depot/Jamgraph'
        self.replicate_sampledir_in_groups_with_docker(
            depot_dir, 1, changing_repinfo_location=True)

        logger.passed(test_case)

    def test_replicate_group_sample_depot_Misc(self):
        test_case = 'replicate_sample_depot_Misc_ingroup'
        depot_dir = '/depot/Misc'
        self.replicate_sampledir_in_groups_with_docker(depot_dir, 3)

        logger.passed(test_case)

    def test_replicate_group_sample_depot_Talkhouse(self):
        test_case = 'replicate_sample_depot_Talkhouse_ingroup'
        depot_dir = '/depot/Talkhouse'
        self.replicate_sampledir_in_groups_with_docker(depot_dir, 5)

        logger.passed(test_case)

    def test_replicate_group_sample_HR(self):
        test_case = 'replicate_sample_HR_ingroup'
        depot_dir = '/HR'
        self.replicate_sampledir_in_groups_with_docker(depot_dir, 1)

        logger.passed(test_case)

    def test_replicate_group_sample_gwt_streams(self):
        test_case = 'replicate_sample_gwt_streams_ingroup'
        depot_dir = '/gwt-streams'
        self.replicate_sampledir_in_groups_with_docker(depot_dir, 7)

        logger.passed(test_case)


if __name__ == '__main__':
    import unittest
    unittest.main()
