import sys
import argparse
import pkgutil
import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "start":
        from autodna.core import engine_start

        sys.argv = ["autodna start", *sys.argv[2:]]
        engine_start.main()
        return

    parser = argparse.ArgumentParser(description="Autonomous DNA Global CLI")
    subparsers = parser.add_subparsers(dest="command", help="The command to run")

    # Dynamic Commands from autodna.tools:
    import autodna.tools
    discovered_tools = []
    for _, module_name, _ in pkgutil.iter_modules(autodna.tools.__path__):
        discovered_tools.append(module_name)
        # Create a proxy subparser for each discovered module to catch the command
        subparser = subparsers.add_parser(module_name, help=f"{module_name.capitalize()} API")
        subparser.add_argument("args", nargs=argparse.REMAINDER)

    args, unknown = parser.parse_known_args()

    if args.command in discovered_tools:
        # Dynamically import and route
        try:
            module = importlib.import_module(f"autodna.tools.{args.command}")
        except ImportError as e:
            print(f"❌ Error: Failed to load tool '{args.command}'. ({e})")
            sys.exit(1)

        # Reconstruct sys.argv passing all unprocessed trailing args directly.
        # sys.argv[0] is the caller (e.g. cli.py), sys.argv[1] is the command.
        # Everything after that belongs to the submodule.
        sys.argv = [f"autodna {args.command}"] + sys.argv[2:]
        module.main()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
