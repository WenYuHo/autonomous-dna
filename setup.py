from setuptools import setup, find_packages

setup(
    name="autodna",
    version="0.1.0",
    description="Autonomous DNA Orchestrator CLI",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "autodna=autodna.cli:main",
        ],
    },
    install_requires=[
        # Add dependencies if needed later (e.g. psutil, requests)
    ],
)
