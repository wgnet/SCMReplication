FROM phusion/baseimage:0.9.8
MAINTAINER Erik Larsson <erik.larsson@musiker.nu>

ENV HOME /root

# Disable SSH
# RUN rm -rf /etc/service/sshd /etc/my_init.d/00_regen_ssh_host_keys.sh

# Use baseimage-docker's init system.
CMD ["/sbin/my_init"]

# Configure apt
RUN echo 'deb http://us.archive.ubuntu.com/ubuntu/ precise universe' >> /etc/apt/sources.list
RUN apt-get -y update

# Install subversion
RUN LC_ALL=C DEBIAN_FRONTEND=noninteractive apt-get install -y subversion

RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Default configuration: can be overridden at the docker command line
ENV SVN_REPONAME repos

EXPOSE 3690

RUN mkdir /etc/service/svn
ADD svn.sh /etc/service/svn/run
RUN chmod u+x /etc/service/svn/run

RUN mkdir -p /var/svn
RUN svnadmin create /var/svn/$SVN_REPONAME
ADD svnserve.conf /var/svn/$SVN_REPONAME/conf/svnserve.conf

# add sample svn repo
ENV SVN_DUMP_FILE svn.apache.org_repos_asf_bigtop.dump
ADD $SVN_DUMP_FILE /root/
RUN svnadmin load /var/svn/$SVN_REPONAME </root/$SVN_DUMP_FILE
RUN /etc/service/svn/run


# To store the data outside the container, mount /svn as a data volume
VOLUME /svn
