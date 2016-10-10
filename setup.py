#!/usr/bin/env python
# -*- coding: utf-8 -*-
import ast
import re

from setuptools import setup, find_packages
from os.path import dirname, join

_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open(join(dirname(__file__), 'tomless.py'), 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(f.read().decode('utf-8')).group(1)))

with open(join(dirname(__file__), 'requirements.txt'), 'rb') as f:
    requires = []
    for line in f.readlines():
        line = line.strip()
        if not line.startswith('#'):
            requires.append(line)
setup(
    name='TOMLess',
    version=version,
    py_modules=['tomless', ],
    # packages=find_packages(exclude=('data', 'log')),
    zip_safe=False,
    entry_points={
        'console_scripts': ['tomless = tomless:execute']
    },
    description="A toml language file parser",
    keywords=("toml parser"),
    include_package_data=True,
    install_requires=requires,
)
