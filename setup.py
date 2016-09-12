#!/usr/bin/env python

from distutils.core import setup

setup(name='dabmsc',
      version='1.0.0',
      description='DAB MSC Datagroup and Packet encoding/decoding',
      author='Ben Poor',
      author_email='ben.poor@thisisglobal.com',
      packages=['msc', 'msc.datagroups', 'msc.packets'],
      package_dir = {'' : 'src'}
      keywords = ['dab', 'msc', 'radio']
     )
