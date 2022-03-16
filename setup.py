#!/usr/bin/env python

from setuptools import setup

setup(name='dabmsc',
      version='1.0.1',
      description='DAB MSC Datagroup and Packet encoding/decoding',
      author='Ben Poor',
      author_email='ben.poor@thisisglobal.com',
      url='https://github.com/GlobalRadio/python-dabmsc',
      download_url='https://github.com/GlobalRadio/python-dabmsc/tarball/1.0.1',
      packages=['msc', 'msc.datagroups', 'msc.packets'],
      package_dir = {'' : 'src'},
      keywords = ['dab', 'msc', 'radio'],
      install_requires = ['bitarray']
     )
