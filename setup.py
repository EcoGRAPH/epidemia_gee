from setuptools import setup

setup(
    # Needed to silence warnings (and to be a worthwhile package)
    name='Epidemia',
    url='',
    author='Ram',
    author_email='Ramcr@ou.edu',
    # Needed to actually package something
    packages=['Ethiopia'],
    # Needed for dependencies
    install_requires=['wget','datetime','requests'],
    version='0.1',
    # The license can be anything you like
    license='GPL-3',
    description='This package helps in getting required environmental data. This package upon executing required functions will directly store data into Google-Drive ',
    
)
