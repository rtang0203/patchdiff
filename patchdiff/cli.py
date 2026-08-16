"""Command line entry point.

Exit codes mirror diff(1): 0 no differences, 1 differences found, 2 error.
That way the tool composes in a shell pipeline.
"""

import argparse
import sys

from .differ import diff_patches
from .model import PatchError
from .parser import load_patch
from .render import render


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="patchdiff",
        description="Show how the application of a patch changes between two "
                    "versions of a patch CSV.",
    )
    parser.add_argument("original", help="path to the existing patch CSV")
    parser.add_argument("updated", help="path to the uploaded patch CSV")
    args = parser.parse_args(argv)

    try:
        diff = diff_patches(load_patch(args.original), load_patch(args.updated))
    except PatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(render(diff))
    return 1 if diff.has_differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
