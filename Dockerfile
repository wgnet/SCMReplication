FROM centos:7

ARG user_uid
ARG user_gid
ARG user_name
ARG group_name
ENV PYTHONPATH=$PYTHONPATH:/application

# add user/group
RUN groupadd -fg $user_gid $group_name
RUN useradd -l -u $user_uid -g $group_name $user_name || true


# install cp1251 to support Russian
RUN localedef -c -f CP1251 -i ru_RU /usr/lib/locale/ru_RU.cp1251

RUN yum install -y gcc \
                   gcc-c++ \
                   python3 \
                   strace \
                   python3-devel \
                   epel-release && \
  yum install -y python36-pysvn \
                   svn \
                   openssl \
                   openssl-devel \
                   openssl-libs \
                   python-pip \
                   glibc.i686 && \
    yum install -y docker git && \
    yum install -y wget 
#    yum clean all


RUN rpm --import https://package.perforce.com/perforce.pubkey
#RUN wget http://filehost.perforce.com/perforce/r18.2/bin.linux26x86_64/p4
#RUN wget http://filehost.perforce.com/perforce/r20.1/bin.linux26x86/p4
#COPY ./p4 /usr/local/bin/
#RUN chmod +rx /usr/local/bin/p4
RUN echo -ne '[perforce]\nname=Perforce\nbaseurl=http://package.perforce.com/yum/rhel/7/x86_64\nenabled=1\ngpgcheck=1\n' > /etc/yum.repos.d/perforce.repo && \
  rpm --import https://package.perforce.com/perforce.pubkey && \
  yum clean all --enablerepo='*' && \
  yum install -y helix-cli &&  yum install -y perforce-p4python3 &&\
  rm -rf /var/cache/yum


RUN rm /usr/bin/python
RUN ln -s /usr/bin/python3 /usr/bin/python

# install required python modules in virtualenv
RUN python3 -m pip install -U pip

#RUN wget -P /tmp http://ftp.perforce.com/pub/perforce/r19.1/bin.linux26x86_64/p4api-glibc2.3-openssl1.0.2.tgz

#RUN wget -P /tmp  http://ftp.perforce.com/pub/perforce/r20.1/bin.linux26x86_64/p4api-glibc2.3-openssl1.0.2.tgz

#RUN tar zxvf /tmp/p4api-glibc2.3-openssl1.0.2.tgz -C /tmp
#RUN ls /tmp
#RUN pip3 install --global-option="build" --global-option="--apidir=$(ls -d /tmp/p4api-2019*)" p4python==2019.1.1858212

RUN mkdir /application || true
RUN groupadd docker && usermod -aG docker $user_name
RUN chown -R $user_name:$group_name /application

COPY ./requirements.txt /application/
RUN pip3 install -r /application/requirements.txt

#USER $user_name
WORKDIR /application

COPY . /application
