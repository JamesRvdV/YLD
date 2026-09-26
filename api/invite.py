"""Create the first admin invitation on the trusted server shell.

The command prints a one-use setup URL. Invitation email is sent only from
the authenticated admin page after this account has set its password.
"""

import argparse

from .main import ADMIN_EMAIL, PUBLIC_URL, issue_invite


def main():
    parser = argparse.ArgumentParser(description="Bootstrap the YLD admin account")
    parser.add_argument("--email", required=True, help=f"Must be {ADMIN_EMAIL}")
    parser.add_argument("--workspace", required=True, help="Admin kitchen name")
    args = parser.parse_args()
    if args.email.strip().lower() != ADMIN_EMAIL:
        parser.error("Only the designated admin account can be bootstrapped here")
    if not PUBLIC_URL.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
        parser.error("YLD_PUBLIC_URL must use HTTPS outside local development")
    try:
        link = issue_invite(args.email, workspace_name=args.workspace, send=False)
    except ValueError as error:
        parser.error(str(error))
    print(link)


if __name__ == "__main__":
    main()
