#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='dabmsc',
      version='1.0.1',
      description='DAB MSC Datagroup and Packet encoding/decoding',
      author='Ben Poor',
      author_email='ben.poor@thisisglobal.com',
      url='https://github.com/GlobalRadio/python-dabmsc',
      download_url='https://github.com/GlobalRadio/python-dabmsc/tarball/1.0.1',
      packages = find_packages(include='src/test'),
      package_dir = {'' : 'src'},
      keywords = ['dab', 'radio'],
      test_suite = "msc.test",
      install_requires = ['bitarray', 'crcmod']
     )
