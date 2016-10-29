import time
import json
import click
import hashlib
import pandas as pd
import pudb
import difflib
import requests
import datetime
import collections
import namedtupled
from copy import deepcopy
from celery.contrib import rdb
from json_tricks.np import loads
from monad.decorators import maybe
from monad.actions import tryout
from os.path import join, isfile
from urllib.parse import urlparse
from urllib.parse import urlencode
from contracts import contract, new_contract
#from maybe import Just, Nothing, lift, maybify
from toolz import compose, partial

from .custom_contracts import *

json.JSONEncoder.default = lambda self,obj: (obj.isoformat() if isinstance(obj, datetime.datetime) else None)
# Implementation of the Maybe monad
#class Maybe:
    #def __init__(self, val, err=None):
        #self.val = val
        #self.err = err
#
    #def __repr__(self):
        #if self.err is not None:
           #return 'Maybe('+repr(self.val)+', '+repr(self.err)+')'
        #else:
           #return 'Maybe('+repr(self.val)+')'
#
    #def do(self, func):  # Bind function
        #if self.val is not None:
            #try:
                #val = func(self.val)
            #except Exception as e:
                #return Maybe(None, e)
            #if not isinstance(val, Maybe):
                #return Maybe(val)
            #else:
                 ##return val
        #else:
            #return Maybe(None, self.err)
#
new_contract('non_empty_tuple', lambda t: isinstance(t, tuple) and len(t)>0)
new_contract('non_empty_list', lambda t: isinstance(t, list) and len(t)>0)
@contract(d='dict', returns='non_empty_tuple')
def tuplify (d):
    od = collections.OrderedDict(sorted(d.items(), key=lambda x: x))
    tup =  tuple([(v, k) for k, v in od.items()])
    return tup
@contract(d='dict', returns='list')
def listify (d):
    od = collections.OrderedDict(sorted(d.items(), key=lambda x: x))
    lst =  [[k,v] for k, v in od.items()]
    return lst

@contract(d='dict', returns='dict')
def order_dict (d):
    od = collections.OrderedDict(sorted(d.items(), key=lambda x: x))
    return od

@contract(returns='str')
def hash_obj(o):
    uni = str(o).encode('utf8')
    hsh = hashlib.sha1(uni).hexdigest()
    return hsh
@contract(p='str', returns='str')
def hash_file(p):
    with open (p, 'rb') as f:
        hsh = hashlib.sha1(f.read()).hexdigest()
    return hsh
def hprogress(it, label=None):
    return click.progressbar(iterable=it,
            fill_char='░',
            label=label,
            show_pos=True,
            show_percent=True,
            color='red',
            )

@contract(df1='isDf',df2='isDf', on='str', how='str')
def merge_fuzzy(df1, df2, on, how, leftovers=None):
    df1 = df1.reset_index(drop=True)
    df2 = df2.reset_index(drop=True)
    _df1 = df1.copy(deep=True)
    _joinCol1 = _df1[on]
    _joinCol2 = list(df2[on])
    # Go through each element of joinCol1 and find the closest
    # element in joinCol2.
    # Copy that element back to joinCol1.
    # Put joinCol1 back into df1 and then perform a
    # vanilla merge.



    for index, row in _df1[on].iteritems():
        closestList = difflib.get_close_matches(row,_joinCol2, n=1, cutoff=0.85)
        if not closestList:
           #print('Could not find any similar string to {} in df2'.format(row))
           continue
        closest = closestList[0]
        _joinCol1.loc[index] = closest

        # Remove from joinCol2 the items already found.
        _joinCol2.remove(closest)

    #if _joinCol2:
        #leftovers = _joinCol2
        #print ('Leftovers in df2:', _joinCol2)

    _df1[on] = _joinCol1

    result = pd.merge(_df1, df2, on=on, how=how)
    return result

#@contract (returns=list)
def flatten (l):
    result = []
    if isinstance (l, list):
        for elem in l:
            if isinstance (l, list):
                result.extend(flatten(elem))
            else:
                result.append(elem)
    else:
        result.append(l)

    return result

def d2l(d):
    l = d.values()
    l = flatten(list(l))
    return l

def isempty(i):
    if isinstance(i, collections.Iterable):
        if len(i) == 0:
            return True
    return False

lmap = lambda f, l: list(map(f, l))

dget = maybe(lambda k, d: dict.get(d, k))

@contract (dates=list)
def nearest_date(dates, pivot):
    closest = min(dates, key=lambda x: abs(x - pivot))
    index = dates.index(closest)
    return closest, index

def timing(f):
    def wrap(*args, **kwargs):
        time1 = time.time()
        ret = f(*args, **kwargs)
        time2 = time.time()
        print ('%s function took %0.3f ms' % (f.__name__, (time2-time1) * 1000.0))
        return ret
    return wrap

def d2nt(dictionary):
    return namedtupled.map(deepcopy(dictionary))

def hjrequest(client, url, rkey, params={}, typ='get', retdf=False):

    if retdf:
        params['asDf'] = True

    if typ == 'get':
        response = client.get(url,
                           data=json.dumps(params),
                           content_type = 'application/json')
    elif typ == 'post':
        response = client.post(url,
                           data=json.dumps(params),
                           content_type = 'application/json')

    responseDict = json.loads(response.get_data().decode('utf-8'))

    code = response.status_code
    message = responseDict['message']
    data = responseDict[rkey]
    if retdf:
        if data:
            data = loads(data, preserve_order=True)
            if data['arr'].any(): # Only make df is array not empty.
                data = pd.DataFrame(data['arr'], columns = data['columns'])
            else:
                data = []

    return code, message, data


#def cached_read_html_page(url, fileName, saveDir, attempted=False):
    #fPath = join(saveDir, '{}.html'.format(fileName))
    #htmlPath = join(savedir, '%s.html' % date)

    #if isfile(fPath):
        #try:
            #with open(fPath, 'rb') as f:
                #page = Just(f.read())
        #except FileNotFoundError:
            #page = Nothing
    #else:
        #try:
            #page = requests.get(url)
            #with open (fPath, 'wb') as f:
                #f.write(page.content)
        #except requests.exceptions.ConnectionError:
            #page = None
        #if not attempted and page is not None:
            #cached_read_html_page(url, fileName, saveDir, attempted=True)
        #else:
            #page = Nothing
    #result = Just(page) if page is not Nothing else page
    #return result


@maybe(nothing_on_exception=requests.exceptions.ConnectionError,
       predicate=lambda p: p.ok)
def request_get(url):
    page = requests.get(url)
    return page

#def maybe_file_write(fPath, contents):
    #if contents is Nothing:
        #result = Nothing
    #else:
        #with open (fPath, 'wb') as f:
            #f.write(contents)
        #result = contents
    #return result
@maybe
def file_write(fPath, contents):
    with open (fPath, 'wb') as f:
        f.write(contents)

    return contents

@maybe(nothing_on_exception=FileNotFoundError)
def file_read(fPath):
    with open(fPath, 'rb') as f:
        result = f.read()
    return result
@maybe
def maybe_getattr(attrName, obj):
    return getattr(obj, attrName)

def cached_read_html_page(url, fPath):
    #maybe_isfile = lift(isfile)
   # requestAndWriteFile = compose (
   #                             partial(file_write, fPath),
   #                             partial(maybe_getattr, 'content'),
   #                             request_get,
   #                       )
    def requestAndWriteFile(url):
        result = request_get(url) >> \
                 partial(maybe_getattr, 'content') >> \
                 partial(file_write, fPath)
        return result

    result = file_read(fPath) or requestAndWriteFile(url)
    return result
