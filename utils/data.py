"""
Saves market data snapshot to DynamoDB.
Simply CSV into JSON into DynamoDB

Author: Peeter Meos, Sigma Research OÜ
Date: 2. December 2018
"""
import boto3
import pandas as pd
import os.path
import json
import decimal
from datetime import datetime


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return str(o)
        return super(DecimalEncoder, self).default(o)


def write_dynamo(filename: str, tbl: str, inst: str):
    """
    Main code for the snapshot upload
    :param filename Filename for CSV data
    :param tbl: Target Dynamo DB table
    :param inst: symbol to be written
    :return: nothing
    """
    mod_time = os.path.getmtime(filename)
    df = pd.read_csv(filename)

    # File modification date
    dtg = datetime.fromtimestamp(mod_time).strftime("%y%m%d%H%M%S")

    # Instrument
    data = df.to_json(orient="split")

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1',
                              endpoint_url="https://dynamodb.us-east-1.amazonaws.com")
    table = dynamodb.Table(tbl)
    response = table.put_item(Item={"dtg": dtg, "inst": inst, "data": json.dumps(data)})

    return response


