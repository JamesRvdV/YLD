"""Send one-use YLD access links from a trusted server shell.

Examples:
  python -m api.invite --email chef@example.com --workspace 'Example Kitchen'
  python -m api.invite --email teammate@example.com --workspace-id WORKSPACE_ID
  python -m api.invite --email you@example.com --workspace 'Sales Demo' --local-link
"""

import argparse

from .main import PUBLIC_URL, issue_invite


def main():
    parser = argparse.ArgumentParser(description="Invite a restaurant to YLD")
    parser.add_argument("--email", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workspace", help="New restaurant name; seeds an isolated sample kitchen")
    group.add_argument("--workspace-id", help="Existing workspace ID for a team member")
    parser.add_argument("--local-link", action="store_true", help="Print instead of email; localhost only")
    args = parser.parse_args()
    if args.local_link and not PUBLIC_URL.startswith(("http://localhost:", "http://127.0.0.1:")):
        parser.error("--local-link is only allowed with a localhost YLD_PUBLIC_URL")
    try:
        link = issue_invite(args.email, workspace_name=args.workspace, workspace_id=args.workspace_id, send=not args.local_link)
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    if args.local_link:
        print(link)
    else:
        print(f"Invitation sent to {args.email.strip().lower()}")


if __name__ == "__main__":
    main()
