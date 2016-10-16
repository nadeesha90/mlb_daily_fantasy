import pudb
from maybe import Just, Nothing, lift
from toolz import thread_first, partial

def add (a, b):
    return a + b

a = Just(1)
b = Just(2)
c = Nothing

maybe_add = lift(add)
d = maybe_add (a,b)
e = maybe_add (a,c)
pu.db
f = a.bind(partial(add, b))

print ("d = ", d)
print ("e = ", type(e))
print ("f = ", f)

