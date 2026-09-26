# Private Hetzner Object Storage media redirects

## Additional work beyond the prompt

None.

## Goal

`https://remite.ax.to/group-a/rehearsal.mp4` asks for the password for
`group-a`, then redirects the browser to a five-minute private Hetzner Object
Storage URL. The tape is downloaded from Hetzner, not `server.swirly.com`.

## Deployment

Run the deployment from this checkout:

```sh
uv run scripts/deploy.py
```

It first asks for group names and passwords. Enter a blank group name, or
`none`, when the list is complete. It then asks for the Cloudflare token. It
uses the default boto3 credentials in `~/.aws` for Hetzner, the `axto-private`
bucket, and the `nbg1` region. Passwords and credentials are never printed in
the confirmation summary. The `remite.ax.to` Virtualmin host must already
exist.

After confirmation, it:

1. Creates or updates the unproxied Cloudflare `A` record for `remite.ax.to`.
2. Creates the bucket if needed, removes its bucket policy, and makes each
   existing object private.
3. Enables Apache CGI support if necessary and installs `boto3` in
   `/home/remite/venv`.
4. Uploads the CGI and its `.htaccess`, writes the server-only Hetzner
   configuration with mode `0600`, and creates `/home/remite/.htpasswd` from
   the group passwords.

The script does not touch `/home/ax/public_html/.htaccess`. It prints the
exact content that belongs there before asking for confirmation and again after
deployment. Copy that content into the existing top-level file yourself.

Use `uv run scripts/deploy.py --dry-run` or `-d` to enter and review a
configuration without making any changes.

## Access model

Each group name becomes both an Apache Basic Auth username and an Object
Storage prefix. For example, `group-a` can access only `group-a/` objects.
Change a group password by running the deployment again with the desired group
list and password. Deleting a group from that list removes its Apache account.

The credentials used by the redirector can read the bucket. Put the bucket in
a dedicated Hetzner project if its other buckets should not share that access.
A person who knows a group password can share it; this is deliberately easy to
use, rather than individual identity authentication.
