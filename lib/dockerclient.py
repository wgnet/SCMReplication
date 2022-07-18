#!/usr/bin/python3

'''docker client interface

This module is implemented on Docker remote API. It assumes that
docker is installed in local machine.

'''

import docker

from .buildlogger import getLogger
#from .localestring import convert_unicode_to_current_locale

logger = getLogger(__name__)


class DockerClient():
    def __init__(self, image, base_url=None, command=None):
        if not base_url:
            base_url = 'unix:///var/run/docker.sock'
        # if not command:
        #    command = '/bin/bash'

        self.command = command
        self.image = image

        self.container = None
        self.container_id = None
#        self.client = docker.from_env()
        self.client = docker.APIClient(base_url=base_url, version='auto')
        # self.client.pull(self.image)

    def create_container(self):
        '''Creates docker container'''
        self.container = self.client.create_container(self.image,
                                                      command=self.command,
                                                      tty=True)
        self.container_id = self.container['Id']

    def delete_container(self):
        '''Removes docker container'''
        self.client.remove_container(self.container_id)

        containers = self.client.containers()
        for container in containers:
            if container['Id'] in self.container_id:
                raise Exception('container not deleted: %s' % str(container))

    def get_container_ip_addr(self):
        '''Returns docker container ip address'''
        if not self.container_id:
            raise Exception('Container not yet created.')

        spec = self.client.inspect_container(self.container_id)
        ip = spec['NetworkSettings']['IPAddress']
#        if type(ip) == unicode:
#        ip = convert_unicode_to_current_locale(ip)

        return ip

    def start_container(self):
        '''Starts docker container'''
        self.client.start(self.container_id)

    def stop_container(self):
        '''Stops docker container'''
        self.client.stop(self.container_id)
