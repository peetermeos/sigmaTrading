"""
Utility functions for GAMS GDX creation

Author: Peeter Meos
Date: 3. December 2018
"""
from gams import GamsDatabase, GamsParameter
import pandas as pd
import json


def create_parameter(db: GamsDatabase, name, desc, uel, form, val):
    """
    Creates multi dimensional parameter array for GAMS GDX export
    :param db: GAMS database object
    :param name: parameter name
    :param desc: parameter description
    :param uel: parameter dimension values
    :param form: sparse or full
    :param val: value object
    :return: Nothing
    """
    v = GamsParameter(db, name, len(uel), desc)
    if form == "full":
        lst = list(uel[0])
        for i in range(0, len(lst)):
            for j in range(0, len(uel[1])):
                v.add_record((lst[i], uel[1][j])).value = float(val.iloc[i, j + 1])
    if form == "sparse":
        for i in uel[0].index:
            v.add_record(uel[0][i]).value = float(val[i])
    return v


def create_scalar(db: GamsDatabase, name, desc, val):
    """
    Creates a GDX structure to represent a scalar
    :param db GAMS database
    :param name: scalar name
    :param desc: explanatory text
    :param val: scalar value
    :return:
    """
    # Add zero-dimensional parameter
    v = db.add_parameter(name, 0, explanatory_text=desc)
    v.add_record().value = float(val)

    return v


def create_set(db: GamsDatabase, name, desc, val, dim=1):
    """
    Creates GAMS set for GDX export
    :param db: Target GAMS database
    :param name: Set name
    :param desc: Explanatory text
    :param val: Set member values
    :param dim: Dimension
    :return:
    """
    # TODO implement that for multidimensional sets
    v = db.add_set(name, dim, explanatory_text=desc)
    for i in val:
        v.add_record(str(i))


def read_gdx_param(db: GamsDatabase, tbl: str) -> pd.DataFrame:
    """
    Reads a table from GDX
    :param db: GAMS Database
    :param tbl: table name to be read
    :return:
    """
    n = []
    lst = []
    for i in db.get_parameter(tbl).domains:
        n.append(i.name)
    for i in db[tbl]:
        d_tmp = {}
        for j in range(0, len(n)):
            d_tmp[n[j]] = i.keys[j]
        d_tmp["val"] = round(i.value, 3)
        lst.append(d_tmp)
    # d = dict((tuple(rec.keys), rec.value) for rec in db[tbl])
    return pd.read_json(json.dumps(lst), orient="records")


def read_gdx_var(db: GamsDatabase, var: str) -> dict:
    """
    Reads a variable from GDX
    :param db: GAMS database
    :param var: variable name to be read
    :return:
    """
    d = dict((tuple(rec.keys), rec.level) for rec in db[var])
    return d
