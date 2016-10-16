import sys
from os.path import dirname, realpath
root = dirname(dirname(realpath(__file__)))
sys.path.append(root)

# Python core modules
import importlib

def get_predictor_obj (predictorName, hypers={}):
    if not predictorName :
            predictorName = 'base'

    moduleName = '%s_predictor' % predictorName.lower()
    className = '%sPredictor' % predictorName.capitalize()
    module = importlib.import_module('dfs_portal.core.predictors.%s' % moduleName)
    predictorClass = getattr(module, '%s' % className )
    pObj = predictorClass (hypers)
    return pObj


if __name__ == '__main__':
    pass
