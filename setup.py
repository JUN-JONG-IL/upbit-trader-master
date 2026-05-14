# !/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- upbit-trader 플랫폼 pip/패키지 배포·설치(setuptools 기반)
- 루트 위치에서 반드시 실행 (pip install ., PyPI등록 등)
"""
import setuptools

install_requires = [
    'pyyaml>=5.4.1',
    'numpy>=1.20.3',
    'matplotlib>=3.4.2',
    'apscheduler>=3.7.0',
    'pymongo>=3.11.4',
    'motor>=2.4.0',
    'mplfinance>=0.12.7a17',
    'pyqt5>=5.15.4',
    'aiopyupbit>=0.1.1',
    'cx_freeze>=6.6'
]

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name='upbit-trader',
    version='0.7.0',
    author='Codejune',
    author_email='kbj9704@gmail.com',
    description='Automatic trader program based on upbit openAPI',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/showmethecoin/upbit-trader',
    packages=setuptools.find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=install_requires,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)