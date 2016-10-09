#!/usr/bin/env python
from setuptools import setup

setup(
    name="apoptosis",
    version="0.1",
    description="Tornado web application for Apoptosis",
    author="Franky Saken",
    author_email="frankysaken@gmail.com",
    url="https://github.com/hrdkx/apoptosis",
    packages=["apoptosis"],
    install_requires=[
        'tornado',
        'sqlalchemy',
        'redis',
        'requests'
    ],
    entry_points={
        'console_scripts': [
            'apoptosis = apoptosis.commands.apoptosis:main'
        ]
    }
)
