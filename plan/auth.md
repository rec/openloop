# Private Hetzner Object Storage media redirects

## Additional work beyond the prompt

None.

## Goal

Serve links such as `https://remite.ax.to/group-a/rehearsal.mp4` to people who
know the group password. Apache authenticates the request, then a small Python
CGI program uses `boto3` to redirect the browser to a five-minute Hetzner
Object Storage URL for that object. The browser downloads the tape directly
from Hetzner, not from `server.swirly.com`.

There are two shared accounts: `group-a` and `group-b`. Each can access only
the S3 prefix with the same name. Change a password in `.htpasswd` to revoke
that group's access. Add additional accounts to the program's prefix mapping
only if individual revocation becomes necessary.

## Hetzner Object Storage setup

1. Keep the bucket private.
2. Create S3 credentials in the Hetzner Console. Keep the access key and
   secret key private. The secret key is shown only once when created.
3. Copy `auth/remite_config.py.example` to `auth/remite_config.py`, and fill
   in the bucket, location, access key, and secret key. Use the Hetzner endpoint
   matching the bucket location, such as `fsn1.your-objectstorage.com`.
   `auth/remite_config.py` is ignored by Git.
4. By default, a Hetzner S3 key can access every bucket in its project. For
   stronger containment, put this bucket in a project dedicated to the
   redirector, or apply a Hetzner bucket policy that allows only the
   redirector's access key. The current design favors easy access, so a
   dedicated project is sufficient.

The policy below is an optional bucket-policy starting point for a dedicated
signing key, replacing `YOUR_BUCKET`, `PROJECT_ID`, and `ACCESS_KEY`:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "AWS": "arn:aws:iam:::user/pPROJECT_ID:ACCESS_KEY"
         },
         "Action": "s3:GetObject",
         "Resource": [
           "arn:aws:s3:::YOUR_BUCKET/group-a/*",
           "arn:aws:s3:::YOUR_BUCKET/group-b/*"
         ]
       }
     ]
   }
   ```

   Hetzner uses principals in the form
   `arn:aws:iam:::user/pPROJECT_ID:ACCESS_KEY`; use that value when applying a
   policy. A separate credentials project is required for a policy that grants
   a key access to a bucket in another project.

## Create the Virtualmin host

First create a DNS `A` or `AAAA` record for `remite.ax.to` pointing to
`server.swirly.com`. The command below deliberately omits `--dns`: `ax.to`
already owns the DNS zone, and creating a second zone for the subdomain would
not add the required record to it.

On `server.swirly.com` as root, create a top-level Virtualmin host. The
password file avoids placing a password in shell history. Create it with mode
`0600` and place a newly chosen Unix/Virtualmin password inside before running
the command.

```sh
virtualmin create-domain \
  --domain remite.ax.to \
  --desc 'Object Storage media redirector' \
  --user remite \
  --passfile /root/remite-virtualmin-password \
  --unix --dir --web --ssl --logrotate --limits-from-plan
```

After the DNS record resolves to this server, request the certificate:

```sh
virtualmin generate-letsencrypt-cert --domain remite.ax.to --web
```

Virtualmin's documented command-line interface runs as root. Its
`create-domain` command creates the Unix account, home directory, web host,
and SSL web host; `generate-letsencrypt-cert` requests the renewable
certificate.

The redirector is CGI. If the uploaded `.htaccess` produces a 500 error,
enable Apache's CGI module once, then reload Apache:

```sh
a2enmod cgid
systemctl reload apache2
```

On distributions using a non-threaded Apache MPM, the module is named `cgi`
instead of `cgid`.

## Install the redirector

1. Run `uv run scripts/deploy.py` locally. It installs `boto3` in
   `/home/remite/venv` as the `remite` user, uploads the CGI program and
   configuration, and installs both Apache `.htaccess` files. It sets the CGI
   program to `0755`, server-only configuration to `0600`, and `.htaccess`
   files to `0644`.
2. Create the two shared passwords. The `-c` flag is used only for the first
   account, because it creates the password file:

   ```sh
   htpasswd -c /home/remite/.htpasswd group-a
   htpasswd /home/remite/.htpasswd group-b
   chown remite:remite /home/remite/.htpasswd
   chmod 640 /home/remite/.htpasswd
   ```

3. Visit a known object at `https://remite.ax.to/group-a/...`. Apache should
   ask for `group-a`'s password and then redirect the browser to Hetzner. A
   `group-b` account must receive HTTP 403 for a `group-a` URL.

## ax.to redirect

`auth/ax.to/.htaccess` is the existing root redirect configuration for
`/home/ax/public_html/.htaccess`. The deployment script installs it with owner
and group `ax:ax`. It retains the `ax.to` to `ax.to/loop` 302 and the existing
`www` canonicalization rule.

## Operational notes

- The link given to people is permanent. Only the Object Storage URL generated
  after a successful password check expires, after five minutes.
- The redirector allows only the two configured prefixes. Rotate or delete its
  Hetzner S3 credentials if the server is compromised.
- A person who knows a group password can share it. This design intentionally
  favors easy access over strong identity verification.
