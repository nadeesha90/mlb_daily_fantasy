import pandas as pd
from pandas.stats import moments

from dfs_portal.utils.htools import d2l

def shift(params, df):
    ''' Shifts targetCol by nPrev times'''
    print('Shifting data')
       #def _shift_data(self, df, targetCol, nPrev, features):
    '''
    Creates X and Y tensors from data timeseries
    '''
    features = params['features']
    targetCol = params['target_col']
    nPrev = params['model']['hypers']['shift_by_days']

    unknownFeatures = features['unknowns']
    knownFeatures   = features['knowns']
    dfX, dfy = df2xy(df, features, targetCol)
    #dfX = df.ix[:,allFeatures]
    #dfy = df.ix[:,[targetCol]]


    ######
    # Batch size = 3
    # Before:   After: y[n] == X[n+3]
    #    |df|  | y| X|
    #    | 0|  | 3| 0|
    #    | 1|  | 4| 1|
    #    | 2|  | 5| 2|
    #    | 3|  | 6| 3|
    #    | 4|  | 7| 4|
    #    | 5|  |NA| 5|
    #    | 6|  |NA| 6|
    #    | 7|  |NA| 7|
    # Drop the last nPrev-1 rows due to batching
    # Can't slice list with -0, so if -nPrev + 1 == 0,
    # return the len of the dataframe.
    sliceIndex = len(df) if (nPrev - 1 == 0) else (-nPrev+1)

    X = dfX
    X = dfX.ix[:,unknownFeatures].iloc[:-nPrev,:]
    _X = dfX.ix[:,knownFeatures].shift(-nPrev)
    _X = _X.iloc[:-nPrev]
    columns = list(_X.columns) + list(X.columns)
    X = pd.concat([_X, X], axis=1, ignore_index=True)
    X.columns = columns

    y = dfy.shift(-nPrev)
    # Chop off the last nPrev rows of y
    y = y.iloc[:-nPrev]


    df = xy2df(X, y)

    return df
def ewma(params, df):
    ''' Ewmas specified columns of the df '''
    print('Ewma data')
    targetCol = params['target_col']
    features = params['features']
    daysToAverage = params['model']['hypers']['days_to_average']
    #unknownFeatures = features['unknowns']
    #knownFeatures   = features['knowns']
    dfX, dfy = df2xy(df, features, targetCol)
    resultDf = pd.DataFrame()
    for col in dfX.columns:
        series = dfX[col]
        # take EWMA in both directions with a smaller span term
        fwd = moments.ewma(series, span=daysToAverage)          # take EWMA in fwd direction
        #bwd = ewma( series[::-1], span=self.daysToAverage )    # take EWMA in bwd direction
        #c = np.vstack(( fwd, bwd[::-1] )) # lump fwd and bwd together
        #c = np.mean( c, axis=0 )          # average
        c = fwd
        cDf = pd.DataFrame(c,columns=[col])
        newDf = pd.concat([resultDf, cDf], axis=1, ignore_index=True)
        columns = list(resultDf.columns)+[col]
        newDf.columns = columns
        resultDf = newDf

    # Attach ewma'd Xs with y and send back df
    dfX = resultDf.round(1)

    df = xy2df(dfX, dfy)

    return df

def df2xy (df, features, targetCol):
    allFeatures = d2l(features)
    dfX = df.ix[:,allFeatures]
    dfy = df.ix[:,[targetCol]]
    return dfX, dfy
def xy2df (dfX, dfy):
    df = pd.concat([dfX, dfy], axis=1, ignore_index=True)
    columns = list(dfX.columns) + list(dfy.columns)
    df.columns = columns
    return df

def get_available_transforms():
    """ Returns the available transforms defined in this module."""
    transforms = ['shift', 'ewma']
    return transforms
