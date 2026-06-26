import os
import sys
from pathlib import Path


def main():
    Path(os.environ["RUNNER_TEMP"], "vexcalibur-query-args.txt").write_text(
        "\n".join(sys.argv[1:]) + "\n",
        encoding="utf-8",
    )
