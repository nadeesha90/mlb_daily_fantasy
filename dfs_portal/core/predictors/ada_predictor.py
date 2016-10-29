# Python core modules
import inspect
from ast import literal_eval
import os
import sys
import traceback#
import pprint
import json
import argparse

from os.path import dirname, realpath
root = dirname(dirname(dirname(realpath(__file__))))
parent_root = dirname(root)
sys.path.append(root)
sys.path.append(parent_root)

#Pypi modules
from joblib import Parallel, delayed
import yaml
import yamlordereddictloader
import pudb
import pdb
from dateutil import parser
from contracts import contract, new_contract, disable_all
from persistent import Persistent
from numpy.random import RandomState
import numpy as np
#import matplotlib.pyplot as plt
# Import datasets, classifiers and performance metrics
from sklearn import datasets, svm, metrics, preprocessing
from sklearn.datasets import make_moons, make_circles, make_classification
from sklearn.linear_model import LassoLarsCV
from sklearn.cross_validation import train_test_split as skttsplit
from sklearn.learning_curve import learning_curve

import pandas as pd
#import tensorflow as tf
#from tensorflow.contrib import learn
from json_tricks.np import dump, dumps, load, loads, strip_comments

#
from toolz import valmap, map, partial, compose, first, pipe, thread_first
from toolz.itertoolz import accumulate, sliding_window
#Custom modules
from dfs_portal.utils.htools import order_dict, timing, d2l
#from dfs_portal.utils.custom_contracts import *
from dfs_portal.core.transforms import df2xy

#disable all contracts
disable_all()
class LassoPredictor (Persistent):
    @contract(hypers='dict')
    def __init__ (self, hypers):
        modelHypers = self.extract_model_hypers(hypers)
        self.model = LassoLarsCV(**modelHypers)

    @timing
    def fit (self, df, features, targetCol, validationSplit=0.2):

        print (df)
        XTrain, yTrain = df2xy(df, features, targetCol)

        success = True
        try:
            self.model.fit(XTrain, yTrain)
        #try:
            #Parallel(n_jobs=2, verbose=10, batch_size=20)(delayed(self.fit_helper)(date) for date in self.dates)
        except ValueError:
            traceback.print_exc()
            success = False
        return success

    def predict (self, df, features, targetCol):
        XPred = df2xy(df, features, targetCol)[0]
        yPred = self.model.predict(XPred)
        df['pred' + targetCol] = yPred
        return df


    #def score (self, userXTest):
    #    # *** Needs reworking!
    #    '''
    #    :returns: Score calculated by taking the last yTrain (all data)
    #    and comparing to predicted result.
    #    '''
    #    if self.modelScore is None:
    #        lastDate = self.dates[-1]
    #        actualY = self.yTrains[lastDate]
    #        #preddf = self.predict(userXTest)
    #        preddf = loads(preddf, preserve_order=True)
    #        preddf = pd.DataFrame(preddf['arr'], columns = [self.targetCol])
    #        predY = preddf[self.targetCol]
    #        predY = predY.shift(-self.batchSize)
    #        predY = predY.iloc[:-self.batchSize]

    #        score = metrics.r2_score(actualY, predY)
    #        self.modelScore = score
    #    else:
    #        score = self.modelScore
    #    return score

    def lc (self):
        '''
        Makes learning curve for a player
        '''
        if self.lcScores is None:

            self.lcModel = LassoLarsCV()
            lastDate = self.dates[-1]
            X = self.XTrains[lastDate]
            y = self.yTrains[lastDate]

            N = len(X)
            chopOff = N - (N % 7)
            X = X.iloc[:chopOff]
            y = y.iloc[:chopOff]
            idxs = np.arange(chopOff)

            cvSplits = [(idxs[:i], idxs[i:]) for i in range(7,chopOff,7)]

            trainSizes, trainScores, testScores = \
                    learning_curve(estimator=self.lcModel,
                                    X=X.as_matrix(),
                                    y=np.array(y),
                                    cv=cvSplits,
                                    train_sizes=[7],
                                    n_jobs=2,
                                    )
            trainSizes = [len(t[0]) for t in cvSplits]
            self.lcScores = dumps((trainSizes, trainScores, testScores))
            result = self.lcScores
        else:
            result = self.lcScores

        return result

    def get_params(self):
        for i, model in self.models.items():
            params = order_dict(model.get_params())
            break
        return params
    def extract_model_hypers (self, hypers):
        '''
        Extracts the parameterse that relevant to the model
        and are not other meta params
        '''
        params = ['verbose']
        modelHypers = {}
        for param in params:
            paramVal = hypers.get(param)
            if paramVal is not None:
                modelHypers[param] = paramVal
        modelHypers = order_dict(modelHypers)
        return modelHypers



if __name__ == '__main__':
    pass

