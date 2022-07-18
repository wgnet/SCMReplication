FROM centos:7

ENV P4PORT 1666
ENV P4ROOT /home/perforce/depot
ENV P4USER testuser
ENV P4PASSWD testuser
ENV P4CLIENT perforce-test

# create Perforce user & group
RUN groupadd p4admin
RUN useradd -m -g p4admin perforce

# Install perforce server and client binaries
ADD http://filehost.perforce.com/perforce/r18.2/bin.linux26x86_64/p4d /usr/local/sbin/
ADD http://filehost.perforce.com/perforce/r18.2/bin.linux26x86_64/p4 /usr/local/bin/
RUN chmod +rx /usr/local/sbin/p4d /usr/local/bin/p4

# From here, everything is done as the perforce user
USER perforce

# Create directory for Perforce depot
RUN mkdir $P4ROOT

# Populate Perforce database from Perforce Sample Depot
# https://community.perforce.com/s/article/2439
RUN mkdir -p /home/perforce/sample && ( curl http://ftp.perforce.com/perforce/tools/sampledepot.tar.gz | tar xz -C /home/perforce/sample ) && cp -Rf /home/perforce/sample/PerforceSample/* $P4ROOT && rm -rf /home/perforce/sample

# Replay from checkpoint
RUN p4d -jr $P4ROOT/checkpoint

# Update database to current version
RUN p4d -xu

# ADD this for debugging -v server=3
ENTRYPOINT p4d

# Expose port
EXPOSE 1666
