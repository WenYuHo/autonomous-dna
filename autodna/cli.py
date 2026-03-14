import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Global CLI")
    subparsers = parser.add_subparsers(dest="command", help="The command to run")
    
    # Start Swarm
    parser_start = subparsers.add_parser("start", help="Start the Autonomous DNA agent swarm in the current repo")
    parser_start.add_argument("--headless", action="store_true", help="Run the swarm in headless background mode")
    
    # Tasks
    parser_tasks = subparsers.add_parser("tasks", help="Tasks management API")
    parser_tasks.add_argument("args", nargs=argparse.REMAINDER)
    
    # Context
    parser_context = subparsers.add_parser("context", help="Architecture memory API")
    parser_context.add_argument("args", nargs=argparse.REMAINDER)
    
    args, unknown = parser.parse_known_args()
    
    if args.command == "start":
        from autodna.core.engine_start import main as engine_main
        sys.argv = [sys.argv[0]]
        if args.headless:
            sys.argv.append("--headless")
        engine_main()
    elif args.command == "tasks":
        import autodna.tools.tasks
        sys.argv = ["autodna tasks"] + (args.args if args.args else []) + unknown
        autodna.tools.tasks.main()
    elif args.command == "context":
        import autodna.tools.context
        sys.argv = ["autodna context"] + (args.args if args.args else []) + unknown
        autodna.tools.context.main()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
