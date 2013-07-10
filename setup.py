#!/usr/bin/env python3

from distutils.core import setup


setup(name='nameless',
      version='0.1',
      description='specialized privacy centric python ircd',
      author='Jeff Becker',
      author_email='ampernand@gmail.com',
      package_dir = { 'nameless' : 'ircd' },
      scripts=['ircd.py'],
      packages=['nameless'])
