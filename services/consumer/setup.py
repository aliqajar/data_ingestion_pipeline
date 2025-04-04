from setuptools import setup, find_packages

setup(
    name="consumer",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "aiokafka==0.12.0",
        "python-dotenv==1.0.1",
        "sqlalchemy==2.0.27",
        "alembic==1.13.1",
    ],
) 