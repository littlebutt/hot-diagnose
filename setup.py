from setuptools import setup, find_packages


def get_version():
    f = open('./VERSION', 'r', encoding='utf-8')
    version = f.readline().strip()
    f.close()
    return version


def get_long_descript():
    f = open('./README.rst', 'r', encoding='utf-8')
    long_descript = f.read()
    f.close()
    return long_descript


if __name__ == '__main__':
    setup(name='hot-diagnose',
          version=get_version(),
          author='littlebutt',
          author_email='luogan1996@icloud.com',
          description="The runtime code diagnose tool",
          long_description=get_long_descript(),
          url='https://github.com/littlebutt/hot-diagnose',
          python_requires='>=3.10',
          packages=find_packages())