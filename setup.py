from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="trading-arena",
    version="1.0.0",
    author="Trading Arena Team",
    description="A comprehensive platform for testing LLM agents as autonomous futures traders on Binance",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lipandarat/trading-arena-system",
    project_urls={
        "Bug Tracker": "https://github.com/lipandarat/trading-arena-system/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "trading-arena=trading_arena.api.main:main",
        ],
    },
    include_package_data=True,
)
