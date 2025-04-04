from setuptools import setup, find_packages

setup(
    name="query",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "fastapi==0.109.2",
        "uvicorn==0.27.1",
        "python-dotenv==1.0.1",
        "sqlalchemy==2.0.27",
        "alembic==1.13.1",
        "redis==5.0.1",
        "cachetools==5.3.2",
        "psycopg2-binary==2.9.9",
    ],
) 