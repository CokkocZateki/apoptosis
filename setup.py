#!/usr/bin/env python
from setuptools import setup

setup(
    name="hkauth",
    version="0.1",
    description="Tornado web application for HKauth",
    author="Franky Saken",
    author_email="frankysaken@gmail.com",
    url="https://github.com/hrdkx/hkauth",
    packages=["hkauth"],
    install_requires=[
        'tornado',
        'sqlalchemy',
        'redis',
        'requests'
    ],
    entry_points={
        'console_scripts': [
            'hkauth = hkauth.commands.hkauth:main'
        ]
    }
)
