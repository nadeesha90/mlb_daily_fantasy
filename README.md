Technologies used:

    * Flask for web-server.
    * Sqlalchemy for ORM.
    * Mysql for production db.
    * sqlite for development db.
    * Celery for launching tasks.
    * Redis for storing celery task information.
## General notes

# Introduction

Setup:
    1. Create a virtualenv.
        `$ virtualenv env`

    2. Install all packages using pip.
        `$ pip install -r requirements.txt`

To run the server, do:
    `$ make run`

This will launch a Flask server and access it from `http://localhost:5000`.

Launch celery tasks in the background for mlbgame update, rotoguru, etc.

    `make celery`






# Redis

`redis-server` must be running for celery tasks to work.
On Mac OSX, run the following command to auto-run `redis-server` on startup.
    `launchctl load ~/Library/LaunchAgents/homebrew.mxcl.redis.plist`
Test if Redis server is running.
    `$ redis-cli ping`

If it replies, `PONG`, you're good~!

