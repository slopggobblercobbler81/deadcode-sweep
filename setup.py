from setuptools import setup, find_packages

setup(
    name="deadcode-sweep",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "deadcode-sweep = deadcode_sweep.cli:main",
        ],
    },
    python_requires=">=3.8",
)
