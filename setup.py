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
    install_requires=['wget','datetime'],
  #  install_requires=['wget'],
  #  install_requires=['subprocess'],
  #  install_requires=['click._compat'],
   # install_requires=['datetime'],
    # *strongly* suggested for sharing
    version='0.1',
    # The license can be anything you like
    license='MIT',
    description='An example of a python package from pre-existing code',
    # We will also need a readme eventually (there will be a warning)
    # long_description=open('README.txt').read(),
)
