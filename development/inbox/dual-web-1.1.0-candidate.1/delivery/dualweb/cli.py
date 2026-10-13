"""Explicit, offline build/check; optional loopback-only HTTP demonstration."""
from __future__ import annotations
import argparse
import json
import sys
from .core import BuildError, build, load_source
from .server import Application, compare_releases, make_server
from . import __version__


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AI-Human Dual Surface Web delivery extension")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check one core-v1.0 public page bundle, offline")
    check.add_argument("source")
    compile_ = commands.add_parser("build", help="create a NEW release directory; never overwrite")
    compile_.add_argument("source")
    compile_.add_argument("--output", required=True)
    compile_.add_argument("--base-path", default="/")
    inspect = commands.add_parser("inspect", help="verify generated files and embedded originals")
    inspect.add_argument("release")
    compare = commands.add_parser("compare", help="compare two complete releases, including deletions")
    compare.add_argument("before")
    compare.add_argument("after")
    serve = commands.add_parser("serve", help="local reference only; not a production server")
    serve.add_argument("release")
    serve.add_argument("--port", default=8765, type=int)
    serve.add_argument("--deny-human", action="store_true",
                       help="deny the HTML surface to ALL callers to test independent AI discovery")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            source = load_source(args.source)
            result = {"status": "passed", "resources": len(source.resources),
                      "scope": "delivery structure only; not truth, full Markdown/YAML semantics, or original PowerShell validation"}
        elif args.command == "build":
            result = build(args.source, args.output, args.base_path)
        elif args.command == "inspect":
            app = Application(args.release)
            result = {"status": "passed", "served_resources": len(app.resources),
                      "scope": "release digest and bundled-source equality"}
        elif args.command == "compare":
            result = compare_releases(args.before, args.after)
        else:
            if not 0 <= args.port <= 65535:
                raise BuildError("port must be between 0 and 65535")
            httpd = make_server(args.release, args.port, deny_human=args.deny_human)
            print(f"Local reference only: http://127.0.0.1:{httpd.server_port}{httpd.application.index_url}", flush=True)
            print("Ctrl+C stops. No bot detection, production authentication or rate limiting.", flush=True)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                httpd.server_close()
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BuildError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
