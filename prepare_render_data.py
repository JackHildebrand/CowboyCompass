"""Download complete OSU datasets; by default prepare every supported term."""
from __future__ import annotations

import argparse
from course_data import TERMS, import_term


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", choices=TERMS, action="append", help="Import only this term (repeatable).")
    args = parser.parse_args()
    for term in args.term or TERMS:
        path = import_term(term)
        print(f"Saved {path.name}.")


if __name__ == "__main__":
    main()
