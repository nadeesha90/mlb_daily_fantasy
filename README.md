Technologies used:

* Flask for web-server.
* Sqlalchemy for ORM.
* Mysql for production db.
* sqlite for development db.
* Celery for launching tasks.
* Redis for storing celery task information.

### General notes

## Introduction

# Setup
0. Purchase Mac.

1. Create a virtualenv.

	`$ virtualenv env`

2. Activate virtualenv.

	`$ source env/bin/activate` 

3. Install all packages using pip.
    
    `$ pip install -r requirements.txt`

4. Fix DataTables module (TEMPORARY).
 
    `$ cp -r pypi_modules/datatables env/lib/python3.5/site-packages`

5. Create database tables.
    `$ ./manage.py create_all`


# Redis

`redis-server` must be running for celery tasks to work. 

6. Install and start redis.

~~~
    $ brew install redis
    $ brew services start redis
~~~
    

7. Copy redis plists.

    `$ cp /usr/local/Cellar/redis/3.2.3/homebrew.mxcl.redis.plist ~/Library/LaunchAgents/`

8. Run the following command to auto-run `redis-server` on startup.
    
    `launchctl load ~/Library/LaunchAgents/homebrew.mxcl.redis.plist`

9. Test if Redis server is running. If it replies, `$ PONG`, you're good~!
    
    `$ redis-cli ping`




# Run server

To run the server, do:

`$ make run`

This will launch a Flask server and access it from `http://localhost:5000`.

Launch celery tasks in the background for mlbgame update, rotoguru, etc.
   
`$ make celery`







