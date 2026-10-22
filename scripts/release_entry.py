"""Frozen entry point, including an opt-in packaged-application self-check."""
import sys

from qpypack.main import main

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from package_smoke import run

        raise SystemExit(run(sys.argv[2]))
    main()
