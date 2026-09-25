"""Send one-use YLD access links from a trusted server shell.

Examples:
  python -m api.invite --email chef@example.com --workspace 'Example Kitchen'
  python -m api.invite --email teammate@example.com --workspace-id WORKSPACE_ID
  python -m api.invite --email you@example.com --workspace 'Your Kitchen' --local-link
  python -m api.invite --email chef@example.com --workspace 'Demo Kitchen' --print-link
"""

import argparse
import os

from .main import PUBLIC_URL, issue_invite


def main():
    parser = argparse.ArgumentParser(description="Invite a restaurant to YLD")
    parser.add_argument("--email", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workspace", help="New restaurant name; starts with an empty workspace")
    group.add_argument("--workspace-id", help="Existing workspace ID for a team member")
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument("--local-link", action="store_true", help="Print instead of email; localhost only")
    delivery.add_argument("--print-link", action="store_true", help="Print a secret one-use link for a trusted preview operator; disabled in production")
    args = parser.parse_args()
    if args.local_link and not PUBLIC_URL.startswith(("http://localhost:", "http://127.0.0.1:")):
        parser.error("--local-link is only allowed with a localhost YLD_PUBLIC_URL")
    if args.print_link and os.getenv("YLD_ENV") == "production":
        parser.error("--print-link is disabled in production")
    if args.print_link and not PUBLIC_URL.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
        parser.error("--print-link requires HTTPS or a localhost YLD_PUBLIC_URL")
    try:
        print_link = args.local_link or args.print_link
        link = issue_invite(args.email, workspace_name=args.workspace, workspace_id=args.workspace_id, send=not print_link)
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    if print_link:
        print(link)
    else:
        print(f"Invitation sent to {args.email.strip().lower()}")


if __name__ == "__main__":
    main()
