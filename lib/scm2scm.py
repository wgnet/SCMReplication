
# class for common replication classes

class ReplicationException(Exception):
    pass

class Replication(object):

    def _calc_start_cl_target_depot_not_exist(self):
        '''case 0: target doesn't exist
        '''
        pass

    def _calc_start_cl_resume_replication(self, rev_in_last_change):
        '''case 1: found replication info from last target changelist

          ---> newer changelsit in target depot --->
          R R ... R R R R R R

          # all replicated changelist
        '''
        if self.source.counter <= rev_in_last_change:
            msg = 'src counter(%s) <= rev in last change(%s), resuming' \
                  ' from %s' % (self.source.counter, rev_in_last_change,
                                rev_in_last_change)
            if hasattr(self, 'logger'):
                self.logger.warning(msg)

            self.source.counter = rev_in_last_change

            return
        else:
            msg = 'src counter(%s) > last replicated ' \
                  'rev (%s)' % (self.source.counter, rev_in_last_change)
            raise ReplicationException(msg)

    def _calc_start_cl_target_depot_has_no_rep_info(self, num_target_revs):
        '''case 2: target exists but found no replication info
        '''
        if self.source.counter:
            return

        msg = 'Target has %s revs but found no rep info.' % num_target_revs
        raise ReplicationException(msg)

    def _calc_start_cl_resume_interrupted_replication(self, last_rep_rev):
        '''case 3, failed to find rep info from last target changelist, but
        found one in previous changes.

          ---> newer changelsit in target depot --->
          R R ... R R R R X X
                          ^^^^ manual commits

        It's either a new replication job or existing one is interrupted.
        '''
        # probably resume an interrupted replication
        if self.source.counter == 0:
            msg = 'src counter is 0(default) while last ' \
                  'replicated rev is %s' % last_rep_rev
            raise ReplicationException(msg)
        elif self.source.counter < last_rep_rev:
            msg = 'src counter(%s) < last replicated rev(%s)' % (
                self.source.counter, last_rep_rev)
            raise ReplicationException(msg)
        else:
            return

    def calc_start_changelist(self):
        '''re-calculate source counter changelist

        scanerios need to be supported:

          case 0: target not exist, start a new replication job

          case 2: target created manually w/o replicaiton script,
          start a new replication job.

          case 1: resume a replication, i.e. we can find rep info in
          the last target change.

          case 3: resume an interrupted replication, cannot find rep
          info in the last target change but in previous changes.

        '''
        # repped_revs: source changelists extracted from target change
        # descriptions. 0 if not a replicated changelist, e.g. a
        # manual submit.
        repped_revs = self.target.get_last_replicated_rev()
        num_target_revs = len(repped_revs)

        # case 0
        target_depot_not_exist = len(repped_revs) == 0
        if target_depot_not_exist:
            self._calc_start_cl_target_depot_not_exist()
            return

        # case 1
        last_repped_rev_in_last_target_changelist = repped_revs[-1] > 0
        if last_repped_rev_in_last_target_changelist:
            last_rep_rev = repped_revs[-1]
            self._calc_start_cl_resume_replication(last_rep_rev)
            return

        # case 2
        # remove slots that has no rep info in desc
        repped_revs = filter(lambda x: x, repped_revs)
        no_rep_info_found_in_target = len(repped_revs) == 0
        if no_rep_info_found_in_target:
            self._calc_start_cl_target_depot_has_no_rep_info(num_target_revs)
            return

        # case 3
        last_rep_rev = repped_revs[-1]
        self._calc_start_cl_resume_interrupted_replication(last_rep_rev)
