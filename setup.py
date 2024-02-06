import logging
import os
from pathlib import Path

from setuptools import Command, setup


class BuildDocsCommand(Command):
    """
    Custom setuptools command to build man page using pandoc.

    Assumes input directory 'doc' and output directory 'man'
    """

    description = "Build documentation with pandoc"
    user_options = []

    def __init__(self, dist, **kw):
        super().__init__(dist, **kw)
        # Create man dir if it does not already exist
        Path("man").mkdir(exist_ok=True)

    def initialize_options(self):
        self.pandoc_files = []

    def finalize_options(self):
        options = self.distribution.get_option_dict("options")
        self.pandoc_files = [f for f in options["pandoc_files"][1].split("\n") if f]

    def run(self):
        for in_file in self.pandoc_files:
            # Assume a filename like 'application.1.md'
            fn, ext = os.path.splitext(in_file)
            # Assume input directory doc and output directory man
            command = [
                "pandoc",
                f"doc/{in_file}",
                "-s",
                "-t",
                "man",
                "-o",
                f"man/{fn}",
            ]
            self.announce("Running command: %s" % " ".join(command), level=logging.INFO)
            self.spawn(command)


if __name__ == "__main__":
    setup(cmdclass={"build_pandoc": BuildDocsCommand})
