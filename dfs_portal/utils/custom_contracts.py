import pandas as pd
from contracts import contract, new_contract, disable_all


@new_contract
def isDf(x):
    return isinstance (x, pd.DataFrame)
