# Private S3 media redirects

## Goal

Serve links such as `https://remite.ax.to/group-a/rehearsal.mp4` to people who
know the group password. Apache authenticates the request, then a small Python
CGI program redirects the browser to a five-minute, read-only S3 URL for that
object. The browser downloads the tape from S3, not from `server.swirly.com`.

There are two shared accounts: `group-a` and `group-b`. Each can access only
the S3 prefix with the same name. Change a password in `.htpasswd` to revoke
that group's access. Add additional accounts to the program's prefix mapping
only if individual revocation becomes necessary.

## AWS setup

1. Keep S3 Block Public Access enabled. Do not make the bucket or its objects
   public.
2. Create an IAM user named `remite-signer` with one access key. Give it only
   `s3:GetObject` on the two required prefixes, replacing `YOUR_BUCKET`:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "s3:GetObject",
         "Resource": [
           "arn:aws:s3:::YOUR_BUCKET/group-a/*",
           "arn:aws:s3:::YOUR_BUCKET/group-b/*"
         ]
       }
     ]
   }
   ```

   Do not grant `s3:ListBucket`, write permissions, or access outside these
   prefixes.
3. Fill in `auth/remite_config.py.example` with the bucket's region, DNS host,
   access-key ID, and secret key. Copy the completed file to
   `/home/remite/remite_config.py` on the server with mode `0600` and ownership
   `remite:remite`. It is deliberately not uploaded or committed.

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
  --desc 'S3 media redirector' \
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

1. Run `auth/upload.sh` locally. It uploads only the public CGI program and
   the two Apache `.htaccess` files. It sets uploaded files to `0644` and
   directories to `0755`; Apache executes the CGI through its handler, so the
   program itself does not need an executable mode.
2. On the server, create `/home/remite/remite_config.py` from the example:

   ```sh
   install -o remite -g remite -m 600 \
     /path/to/completed/remite_config.py /home/remite/remite_config.py
   ```

3. Create the two shared passwords. The `-c` flag is used only for the first
   account, because it creates the password file:

   ```sh
   htpasswd -c /home/remite/.htpasswd group-a
   htpasswd /home/remite/.htpasswd group-b
   chown remite:remite /home/remite/.htpasswd
   chmod 640 /home/remite/.htpasswd
   ```

4. Visit a known object at `https://remite.ax.to/group-a/...`. Apache should
   ask for `group-a`'s password and then redirect the browser to S3. A
   `group-b` account must receive HTTP 403 for a `group-a` URL.

## ax.to redirect

`auth/ax.to/.htaccess` is the existing root redirect configuration for
`/home/ax/public_html/.htaccess`. `auth/upload.sh` installs it with owner and
group `ax:ax`. It retains the `ax.to` to `ax.to/loop` 302 and the existing
`www` canonicalization rule.

## Operational notes

- The link given to people is permanent. Only the S3 URL generated after a
  successful password check expires, after five minutes.
- The signing key may issue URLs only for the two configured prefixes. Rotate
  or disable that IAM access key if the server is compromised.
- A person who knows a group password can share it. This design intentionally
  favors easy access over strong identity verification.
