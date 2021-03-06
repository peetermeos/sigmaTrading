"""
Snapshot scraper.
Code connects to TWS and saves snapshot data for instruments
into Dynamo. Ported from Java

Author: Peeter Meos, Sigma Research OÜ
Date: 11. December 2018
"""
from ibapi.contract import Contract, ContractDetails
from ibapi.wrapper import TickType, TickAttrib
from tws.tws import TwsTool
from datetime import datetime
from dateutil.relativedelta import relativedelta
from tws import tools
from utils import logger
import pandas as pd
import numpy as np
import time
import boto3
import argparse
import json

"""
The necessary columns are:
Financial Instrument            CL FOP (LO) Feb'19 40 CALL @NYMEX
Underlying Price                51.54
Bid                             11.61
Mid                             11.649999999999999
Ask                             11.69
Spread                          0.08
Position
Avg Price
Implied Vol. %                  50.8%
Delta                           0.964931
Gamma                           0.010373
Vega                            0.012236
Theta                           -0.008877
Days to Last Trading Day        30.0
"""


class Snapshot(TwsTool):
    """
    Class implements option chain snapshot data request and retrieval logic from TWS
    """
    def __init__(self, config=None, log_level=logger.LogLevel.normal):
        """
        Standard constructor for the class
        """
        super().__init__(name="Snapshot Scraper", log_level=log_level)

        self.config = config

        self.chain = []
        self.months = []
        self.account = {}
        self.strikes = []
        self.df = pd.DataFrame()

        self.p_from = float(config["price.from"])
        self.p_to = float(config["price.to"])
        self.p_step = float(config["price.step"])
        self.acct_updates_ongoing = True

        # TODO: The forward month calculation should be automatic, so for instance it should know when
        #   in December to go still for Jan contract and when start from Feb. Ie. the calculation on those
        #   months should be based on real last trading dates that we currently don't have
        m_start = int(config["rel.start.month"])
        m_step = int(config["rel.step.month"])
        for i in range(m_start, int(config["months"])+m_start, m_step):
            tmp = datetime.today() + relativedelta(months=+i)
            self.months.append(tmp.strftime("%Y%m"))

        self.cont = Contract()
        if config is None:
            self.cont.symbol = "CL"
            self.cont.exchange = "NYMEX"
            self.cont.currency = "USD"
            self.cont.secType = "FOP"
            self.cont.tradingClass = "LO"
        else:
            self.cont.symbol = config["symbol"]
            self.cont.exchange = config["exchange"]
            self.cont.currency = config["currency"]
            self.cont.secType = config["sectype"]
            self.cont.tradingClass = config["class"]

    def create_instruments(self):
        """
        Creates instruments
        :return:
        """

        self.logger.log("Creating instruments and requesting data")

        # This updates portfolio positions, also saves strikes
        self.acct_updates_ongoing = True
        self.reqAccountUpdates(True, self.config["account"])
        # We need to wait for account updates to finish, before we start requesting option chain data.
        while self.acct_updates_ongoing:
            time.sleep(0.1)
        # Now find maximum and minimum strike and update if needed
        for key, item in self.account.items():
            self.p_to = max(self.p_to, float(item["strike"]))
            self.p_from = min(self.p_from, float(item["strike"]))

        self.logger.verbose("Price range min: " + str(self.p_from) + " max: " + str(self.p_to))
        self.strikes = np.array(range(0, int(round((self.p_to - self.p_from) /
                                                   self.p_step)))) * self.p_step + self.p_from

        sides = ["c", "p"]
        o = int(self.nextId) + 1
        for m in self.months:
            self.logger.log("Requesting month " + m)
            for i in self.strikes:
                for j in sides:
                    str_s = "CALL" if str(j) == "c" else "PUT"
                    str_f = self.cont.symbol + " " + self.cont.secType + " ("
                    str_f += self.cont.tradingClass + ") "
                    str_f += datetime.strptime(m, "%Y%m").strftime("%b'%y")
                    str_f += " " + "{:g}".format(i) + " "
                    str_f += str_s + " @" + self.cont.exchange
                    self.chain.append({"id": o,
                                       "Financial Instrument": str_f,
                                       "Strike": i,
                                       "Side": j.upper(),
                                       "Expiry": m,
                                       "Underlying Price": float('nan'),
                                       "Bid": float('nan'),
                                       "Ask": float('nan'),
                                       "Delta": float('nan'),
                                       "Gamma": float('nan')})
                    self.cont.right = j.upper()
                    self.cont.strike = i
                    self.cont.lastTradeDateOrContractMonth = m

                    time.sleep(1/40)
                    self.reqMktData(o, self.cont, genericTickList="",
                                    snapshot=True, regulatorySnapshot=False,
                                    mktDataOptions=[])
                    self.reqContractDetails(o, self.cont)
                    o = o + 1

    def tickPrice(self, req_id: int, tick_type: TickType, price: float,
                  attrib: TickAttrib):
        """
        Market tick data override for snapshot market data retrieval
        :param req_id:
        :param tick_type:
        :param price:
        :param attrib:
        :return:
        """
        for i in self.chain:
            if i["id"] == req_id:
                if tick_type == 1:
                    i["Bid"] = price
                elif tick_type == 2:
                    i["Ask"] = price

    def contractDetails(self, req_id: int, contract_details: ContractDetails):
        """
        Contract details reception override
        :param req_id:
        :param contract_details:
        :return:
        """
        for i in self.chain:
            if req_id == i["id"]:
                i["conid"] = contract_details.contract.conId
                i["Days to Last Trading Day"] = contract_details.contract.lastTradeDateOrContractMonth

    def tickOptionComputation(self, req_id: int, tick_type: TickType,
                              implied_vol: float, delta: float, opt_price: float, pv_dividend: float,
                              gamma: float, vega: float, theta: float, und_price: float):
        """
        Option computation and greek data retrieval override for saving the snapshot data.
        :param req_id:
        :param tick_type:
        :param implied_vol:
        :param delta:
        :param opt_price:
        :param pv_dividend:
        :param gamma:
        :param vega:
        :param theta:
        :param und_price:
        :return:
        """
        found = False
        for i in self.chain:
            if i["id"] == req_id:
                found = True
                if und_price is not None:
                    i["Underlying Price"] = und_price
                else:
                    print(i["Financial Instrument"])
                if tick_type == 13:
                    i["Delta"] = delta
                    i["Gamma"] = gamma
                    i["Theta"] = theta
                    i["Vega"] = vega
                    i["Implied Vol. %"] = "NA" if implied_vol is None else str(implied_vol * 100) + "%"
        if not found:
            self.logger.error("Unknown req id in option computation tick!")

    def updatePortfolio(self, contract: Contract, position: float,
                        market_price: float, market_value: float,
                        average_cost: float, unrealized_pnl: float,
                        realized_pnl: float, account_name: str):
        """
        Account position update override
        :param contract:
        :param position:
        :param market_price:
        :param market_value:
        :param average_cost:
        :param unrealized_pnl:
        :param realized_pnl:
        :param account_name:
        :return:
        """
        if contract.symbol == self.cont.symbol:
            self.account[contract.conId] = {"position": position,
                                            "avg price": average_cost,
                                            "strike": contract.strike}

    def accountDownloadEnd(self, account_name: str):
        """
        End of account data download
        :param account_name:
        :return:
        """
        self.logger.verbose("All account data for " + account_name + " received.")
        self.acct_updates_ongoing = False

    def wait_to_finish(self):
        """
        Waits until all margin data has been received
        :return:
        """
        self.logger.log("Waiting for all market data to arrive")
        found = False
        c1 = 0
        while not found:
            c_prev = c1
            c1 = 0
            found = True

            for i in self.chain:
                if (np.isnan(i["Ask"]) and np.isnan(i["Bid"])) or i["Delta"] == float("nan"):
                    found = False
                    c1 = c1 + 1
            self.logger.log(str(c1) + " instruments of " + str(len(self.chain)) + " missing")
            time.sleep(0.5)
            # Break loop when two loops in a row are with same missing rows
            if c_prev == c1:
                break

        self.logger.log("All available data has been received, proceeding")

    def prepare_df(self):
        """
        Prepares market snapshot data frame for export
        :return:
        """
        df = pd.DataFrame(self.chain)
        df["Mid"] = (df["Ask"] + df["Bid"]) / 2
        df["Spread"] = np.abs(df["Ask"] - df["Bid"])
        df["Days to Last Trading Day"] = pd.to_datetime(df["Days to Last Trading Day"],
                                                        format="%Y%m%d") - datetime.today()
        df["Days to Last Trading Day"] = df["Days to Last Trading Day"].dt.days

        df["Position"] = 0
        df["Avg Price"] = 0

        self.logger.log("Getting contract IDs from Dynamo DB")
        df = tools.lookup_contract_id(df, "instruments")

        self.logger.log("Updating account position data")
        # Now loop through the account dict and update the position data
        for k, v in self.account.items():
            df.loc[df["conid"] == k, "Position"] = v["position"]
            df.loc[df["conid"] == k, "Avg Price"] = v["avg price"] / float(self.config["mult"])

        self.df = df
        return df

    def export_dynamo(self, tbl="mktData"):
        """
        Exports the data to dynamoDB
        :param tbl: Dynamo DB table to write the margins to
        :return:
        """

        self.logger.log("Exporting market data snapshot to Dynamo DB table " + str(tbl))
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1',
                                  endpoint_url="https://dynamodb.us-east-1.amazonaws.com")
        table = dynamodb.Table(tbl)
        mod_time = datetime.today()
        dtg = mod_time.strftime("%y%m%d%H%M%S")

        # Instrument
        data = self.df.to_dict(orient="split")
        data["dtg"] = int(dtg)
        data["inst"] = self.cont.symbol
        data["data"] = json.dumps(data["data"])

        response = table.put_item(Item=data)

        is_ok = response["ResponseMetadata"]["HTTPStatusCode"] == 200
        if is_ok:
            self.logger.verbose("Data export to DynamoDB successful")
        else:
            self.logger.error("Failed to export data to DynamoDB")


if __name__ == "__main__":
    # Process command line arguments first
    parser = argparse.ArgumentParser("Market data capture tool")
    parser.add_argument("-v", "--verbose", action="store_true", help="Produce verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Minimal logging, only output errors")
    parser.add_argument("--db", action="store_true", help="Write snapshot to Dynamo DB")
    parser.add_argument("--csv", action="store", help="Write snapshot to given CSV file")

    args = parser.parse_args()

    # Now the actual stuff
    tws = Snapshot()

    tws.connect("localhost", 4001, 12)
    tws.create_instruments()
    tws.wait_to_finish()
    df1 = tws.prepare_df()
    df1.to_csv("./data/out.csv", index=None)
    tws.export_dynamo()
    tws.disconnect()
