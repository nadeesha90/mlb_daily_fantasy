from dfs_portal.utils.ctools import wait_for_task, cResult, cStatus
from dfs_portal.extensions import celery, db, redis
import random
import time

@celery.task(bind=True)
def long_task(self):
    """Background task that runs a long function with progress reports."""
    verb = ['Starting up', 'Booting', 'Repairing', 'Loading', 'Checking']
    adjective = ['master', 'radiant', 'silent', 'harmonic', 'fast']
    noun = ['solar array', 'particle reshaper', 'cosmic ray', 'orbiter', 'bit']
    message = ''
    total = 100
    for i in range(total):
        time.sleep(2)
        if not message or random.random() < 0.25:
            message = '{0} {1} {2}...'.format(random.choice(verb),
                                              random.choice(adjective),
                                              random.choice(noun))
        self.update_state(state='PROGRESS', meta=cResult(result=dict(name='long_task', data=dict(current=i,total=total)), status=cStatus.success))
    return cResult(result=dict(name='long_task', message='Finished!', data='ree'), status=cStatus.success)
