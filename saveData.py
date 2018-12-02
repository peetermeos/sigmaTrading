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
import sys
from datetime import datetime


def write_data(filename: str):
    """
    Main code for the snapshot upload
    :param filename Filename for CSV data
    :return:
    """
    mod_time = os.path.getmtime(filename)
    df = pd.read_csv(filename)

    # File modification date
    dtg = datetime.fromtimestamp(mod_time).strftime("%y%m%d%H%M%S")

    # Instrument
    inst = "CL"
    data = df.to_json(orient="split")

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1',
                              endpoint_url="https://dynamodb.us-east-1.amazonaws.com")
    table = dynamodb.Table("mktData")
    response = table.put_item(Item={"dtg": dtg,
                                    "inst": inst,
                                    "data": json.dumps(data)})

    return response


if __name__ == "__main__":
    """
    Main entry point for the program
    """
    write_data(sys.argv[1])