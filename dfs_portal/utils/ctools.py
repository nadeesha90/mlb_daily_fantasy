import time
import pudb
from collections import namedtuple

from celery.task.control import inspect
from celery.backends.database.models import *
from celery.backends.database import session

from dfs_portal.schema.core import celery_result_schema

def wait_for_task(task, taskName, waitUpTo, sleepFor):
    '''
    Takes a celery task and returns either the result from each task
    or an error code.
    '''
    # Attempt to obtain the result.
    for _ in range(int(waitUpTo / sleepFor)):
        time.sleep(sleepFor)
        if not task.ready():
            continue  # Task is still running.
        result = task.get(propagate=False)
        if isinstance(result, Exception):
            # The task crashed probably because of a bug in the code.
            if str(result) == 'Failed to acquire lock.':
                # Never mind, no bug. The task was probably running from Celery Beat when the user tried to run a second
                # instance of the same task.
                # Since the user is expecting this task to update the database, we'll tell them that results should be
                # updated within the minute, since the previously-running task should finish shortly.
                #return redirect(url_for('.index'))
                resObj, err = celery_result_schema.load(
                    dict(name=taskName,
                         data=None,
                         status='locked',
                         msg='',
                         currentProgress=0,
                         totalProgress=1,
                    )
                )
                return resObj
            resObj, err = celery_result_schema.load(
                    dict(name=taskName,
                         data=None,
                         status='fail',
                         msg=result.__repr__(),
                         currentProgress=0,
                         totalProgress=1,
                    )
                )
            return resObj

        return result
    resObj, err = celery_result_schema.load(
                    dict(name=taskName,
                         data=None,
                         status='none',
                         msg='Timed out',
                         currentProgress=0,
                         totalProgress=1,
                    )
                )
    return resObj
