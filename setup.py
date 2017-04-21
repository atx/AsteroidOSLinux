#! /usr/bin/env python3

from setuptools import setup

setup(
    name="asteroid",
    version="0.1",
    packages=["asteroid"],
    scripts=["./asteroid-linux.py"],
    description="Python library+tools for AsteroidOS smart watches",
    author="Josef Gajdusek",
    author_email="atx@atx.name",
    url="https://github.com/atalax/AsteroidOSLinux.git",
    license="MIT",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Utilities"
    ]
)
