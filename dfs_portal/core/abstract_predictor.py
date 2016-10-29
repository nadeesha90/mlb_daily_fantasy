# Python core modules
import importlib
import pkgutil

def get_predictor_obj (predictorName, hypers={}):
    if not predictorName :
            predictorName = 'base'

    moduleName = '%s_predictor' % predictorName.lower()
    className = '%sPredictor' % predictorName.capitalize()
    module = importlib.import_module('dfs_portal.core.predictors.%s' % moduleName)
    predictorClass = getattr(module, '%s' % className )
    pObj = predictorClass (hypers)
    return pObj

def get_available_predictors():
    parent = importlib.import_module('dfs_portal.core.predictors')
    predictors = [name.replace('_predictor', '') for _, name, _ in pkgutil.walk_packages(parent.__path__)]

    return predictors
if __name__ == '__main__':
    pass
