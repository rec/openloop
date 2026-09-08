#!/usr/bin/env bash

rsync -av -e ssh \
  --chown=ax:ax \
  /Users/tom/code/openloop/index.html \
  /Users/tom/code/openloop/open-loop.mp4 \
  /Users/tom/code/openloop/favicon.png \
  'root@server.swirly.com:~ax/public_html/loop/'
