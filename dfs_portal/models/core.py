from enum import Enum

class cStatus(Enum):
    fail = 1
    locked = 2
    success = 3
    none = 4

class CeleryResult(object):
    def __init__(self, name, currentProgress, totalProgress, status, data=None, msg=None):
        self.name = name
        self.data = data
        self.status = status
        self.msg = msg
        self.currentProgress = currentProgress
        self.totalProgress = totalProgress


    def __repr__(self):
        return 'CeleryResult({},data={},msg={})'.\
            format(self.status,self.data, self.msg)
