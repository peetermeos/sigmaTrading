"""
Code to handle portfolio snapshots, overviews and everything related.

Author: Peeter Meos
Date: 2. January 2019
"""
from tws import TwsTool
from utils.logger import LogLevel
from ibapi.contract import Contract
from ibapi.wrapper import TickType, TickerId
from ibapi.account_summary_tags import AccountSummaryTags
import time


class Portfolio(TwsTool):
    def __init__(self, acct, log_level=LogLevel.normal):
        super().__init__("Portfolio", log_level=log_level)
        self.haveData = False
        self.acct = acct
        self.portfolio = []
        self.value = 0.0

    def get_account_summary(self):
        """
        Simply prints out account summary
        :return:
        """
        self.connect("localhost", 4001, 32)
        self.haveData = False

        self.logger.log("-------------- Account --------------")
        self.reqAccountSummary(self.nextId, "All", AccountSummaryTags.AllTags)
        while not self.haveData:
            time.sleep(0.01)
        self.logger.log("-------------------------------------")
        self.disconnect()

    def get_account_details(self):
        """
        Simply prints out account details
        :return:
        """
        self.connect("localhost", 4001, 32)
        self.haveData = False

        self.logger.log("-------------- Account --------------")
        self.reqAccountUpdates(True, self.acct)
        while not self.haveData:
            time.sleep(0.01)
        self.logger.log("-------------------------------------")
        self.reqAccountUpdates(False, self.acct)
        self.disconnect()

    def get_snapshot(self):
        """
        Gets portfolio snapshot and does a summary on that
        :return:
        """
        # TODO: Get rid of those hardcoded parameters, use config file instead
        self.connect("localhost", 4001, 32)

        """
        self.reqAccountUpdates(True, self.acct)
        while not self.haveData:
            time.sleep(0.01)
        self.reqAccountUpdates(False, self.acct)

        """


        # TODO: Add snapshot summary here, like total unrealised PNL
        """
        self.haveData = False
        o = self.nextId
        for i in self.portfolio:
            i["id"] = o
            self.reqMktData(o, i["cont"], "", True, False, [])
            o += 1

        
        # Wait until we have all the data
        while not self.haveData:
            time.sleep(0.1)
        """

        """
        # Now cancel the mkt data and do some cleanup
        for i in self.portfolio:
            self.cancelMktData(i["id"])

        """
        self.disconnect()

    def updateAccountValue(self, key: str, val: str, currency: str, account_name: str):
        """
        Account value update overload
        :param key:
        :param val:
        :param currency:
        :param account_name:
        :return:
        """
        #if account_name == self.acct:
        self.logger.log(key.ljust(30) + "\t" + val.rjust(10) + " " + currency)

    def updatePortfolio(self, contract: Contract, position: float, market_price: float, market_value: float,
                        average_cost: float, unrealized_pnl: float, realized_pnl: float, account_name: str):
        """
        Portfolio contents update overload
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
        # if account_name == self.acct:
        self.logger.log(contract.symbol.ljust(5) + " " + str(position).rjust(6) + " " +
                        str(round(market_price, 3)).rjust(5) +
                        " " + str(unrealized_pnl).rjust(10))
        self.portfolio.append({"cont": contract})

    def accountSummary(self, req_id: int, account: str, tag: str, value: str, currency: str):
        """
        Account summary information
        :param req_id:
        :param account:
        :param tag:
        :param value:
        :param currency:
        :return:
        """
        self.logger.log(tag.ljust(25) + "\t" + value + " " + currency)

    def accountSummaryEnd(self, req_id: int):
        """
        End of account summary
        :param req_id:
        :return:
        """
        self.haveData = True

    def accountDownloadEnd(self, account_name: str):
        """
        My override of end of account download details
        :param account_name:
        :return:
        """
        #if account_name == self.acct:
        self.haveData = True

    def tickOptionComputation(self, req_id: TickerId, tick_type: TickType, implied_vol: float, delta: float,
                              opt_price: float, pv_dividend: float, gamma: float, vega: float, theta: float,
                              und_price: float):
        """
        Save the greeks
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
        for i in self.portfolio:
            if i["id"] == int(req_id):
                i["Delta"] = delta
                i["Gamma"] = gamma
                i["Theta"] = theta
                i["Vega"] = vega


