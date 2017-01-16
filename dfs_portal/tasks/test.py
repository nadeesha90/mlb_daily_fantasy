from dfs_portal.utils.ctools import wait_for_task
from dfs_portal.schema.core import celery_result_schema
from dfs_portal.extensions import celery, db, redis
from celery.contrib import rdb
import random
import time

@celery.task(bind=True)
def long_task(self):
    """Background task that runs a long function with progress reports."""
    verb = ['Starting up', 'Booting', 'Repairing', 'Loading', 'Checking']
    adjective = ['master', 'radiant', 'silent', 'harmonic', 'fast']
    noun = ['solar array', 'particle reshaper', 'cosmic ray', 'orbiter', 'bit']
    message = ''
    total = 10
    for i in range(total):
        time.sleep(1)
        if not message or random.random() < 0.25:
            message = '{0} {1} {2}...'.format(random.choice(verb),
                                              random.choice(adjective),
                                              random.choice(noun))
        resObj, err = celery_result_schema.load(
                dict(name='long_task',
                     data=None,
                     status='locked',
                     msg='',
                     currentProgress=i,
                     totalProgress=total,
                )
            )
        self.update_state(state='PROGRESS', meta=resObj)

    resObj, err = celery_result_schema.load(
                dict(name='long_task',
                     data='REE',
                     status='success',
                     msg='Complete!',
                     currentProgress=total,
                     totalProgress=total,
                )
            )
    return resObj
