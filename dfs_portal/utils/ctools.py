import time
import pudb
from collections import namedtuple
from enum import Enum
class cStatus(Enum):
    fail = 1
    locked = 2
    success = 3
    none = 4

cResult = namedtuple('cResult', 'result, status')



def wait_for_task(task, wait_up_to, sleep_for):
    '''
    Takes a celery task and returns either the result from each task
    or an error code.
    '''
    # Attempt to obtain the result.
    for _ in range(int(wait_up_to / sleep_for)):
        time.sleep(sleep_for)
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
                return cResult(result=None, status=cStatus.locked)
            return cResult(result=None, status=cStatus.fail)

        return result

    return cResult(result=None, status=cStatus.none)
