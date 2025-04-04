from setuptools import setup, find_packages

setup(
    name="collector",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "aiohttp==3.9.3",
        "aiokafka==0.12.0",
        "python-dotenv==1.0.1",
        "sqlalchemy==2.0.27",
        "redis==5.0.1",
    ],
) 