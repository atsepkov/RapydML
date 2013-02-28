from setuptools import setup, find_packages

DESCRIPTION = 'Python-based XML/HTML Compiler'

LONG_DESCRIPTION = """
RapydML
===========

RapydML is a Pythonic abstraction of XML/HTML, adding more 
functionality, ability to easily integrate it with any HTML
templating framework, and create your own subset of XML whose
rules will be enforced through RapydML compiler.


Installation
------------
To install RapydML simply use easy_install or pip:

    pip install rapydml

or

    easy_install rapydml


License
-------
The project is GPLv3, but the output is license free. 
See http://www.gnu.org/licenses/gpl-faq.html#WhatCaseIsOutputGPL.

"""

setup(name='rapydml',
      version='0.0.1',
      packages=['rapydml'],
      package_data={'rapydml': ['*.txt', 'lib/*', 'markup/*']},
      author='Alexander Tsepkov',
      url='http://rapydml.pyjeon.com',
      description=DESCRIPTION,
      long_description=LONG_DESCRIPTION,
      platforms=['any'],
      license='GNU GPL3',
      install_requires=[],
      scripts=['bin/rapydml']
)

