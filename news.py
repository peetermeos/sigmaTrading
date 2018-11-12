"""
News trader implementation in Python

Peeter Meos, 8. November 2018
"""
from threading import Thread
from typing import List
import time
from ibapi.client import *
from ibapi.wrapper import *
from logger import *


class TraderStatus(Enum):
    """
    Statuses are as follows:
    COLD - trader is not on the market, no orders
    HOT - trader is on the market, with orders waiting for execution
    ACTIVE - at least one of the orders has been executed, we have a nonzero position
    """
    COLD = 1
    HOT = 2
    ACTIVE = 3


class TwsClient(EClient):
    """
    EClient extension for news trader
    """
    def __init__(self, wrapper):
        """
        Simple constructor for the client
        :param wrapper:
        """
        EClient.__init__(self, wrapper)


class TwsWrapper(EWrapper):
    """
    EWrapper extension for news trader
    """
    def __init__(self):
        """
        Simple constructor for the wrapper
        Also handles creation and initialisation of orders for the
        trading strategy
        """

        # First lets get started with logging
        self.logger = Logger(LogLevel.normal, "Wrapper")
        self.logger.log("Wrapper init")
        EWrapper.__init__(self)
        self.nextValidOrderId = -1

        # The settings for the order structure
        # At some later stage this also needs to be dynamic and be set somewhere else
        self.last_price = -1.0              # Last known price of the instrument
        self.set_price = -1.0               # The price that the order structure is set at
        self.entry_spread = 0.05            # Spread for the order structure
        self.tgt_spread = 0.2               # Target distance
        self.trail_spread = 0.2             # Trailing stop distance
        self.delta_adjust = 0.02            # After how much movement adjust price
        self.time_adjust = 500              # Time step (ms) for order adjustment
        self.q = 1                          # Order quantity
        self.status = TraderStatus.COLD     # Set default trader status

        # Initialize orders
        self.logger.log("Initialising the order structure")
        self.long_entry = Order()
        self.long_tgt = Order()
        self.long_trail = Order()

        self.short_entry = Order()
        self.short_tgt = Order()
        self.short_trail = Order()

        # Long entry
        self.long_entry.action = "BUY"
        self.long_entry.orderType = "STP LMT"
        self.long_entry.totalQuantity = self.q
        self.long_entry.transmit = False

        # Long target
        self.long_tgt.action = "SELL"
        self.long_tgt.orderType = "LMT"
        self.long_tgt.totalQuantity = self.q
        self.long_tgt.transmit = False
        self.long_tgt.ocaGroup = "News_Long"

        # Long trail
        self.long_trail.action = "SELL"
        self.long_trail.orderType = "TRAIL"
        self.long_trail.totalQuantity = self.q
        self.long_trail.ocaGroup = "News_Long"
        self.long_trail.transmit = False  # Should be true

        # Short entry
        self.short_entry.action = "SELL"
        self.short_entry.orderType = "STP LMT"
        self.short_entry.totalQuantity = self.q
        self.short_entry.transmit = False

        # Short target
        self.short_tgt.action = "BUY"
        self.short_tgt.orderType = "LMT"
        self.short_tgt.totalQuantity = self.q
        self.short_tgt.ocaGroup = "News_Short"
        self.short_tgt.transmit = False

        # Short trail
        self.short_trail.action = "BUY"
        self.short_trail.orderType = "TRAIL"
        self.short_trail.totalQuantity = self.q
        self.short_trail.ocaGroup = "News_Short"
        self.short_trail.transmit = False  # Should be true

    def nextValidId(self, order_id: int):
        """
        Updates the next valid order ID, when called by the API
        :param order_id: given by the TWS API
        :return: nothing
        """
        super().nextValidId(order_id)
        self.logger.log("Setting nextValidOrderId: "+str(order_id))
        self.nextValidOrderId = int(order_id)

    def get_orders(self) -> List[Order]:
        """
        Returns orders as a list
        :return: list of orders
        """
        return [self.long_entry, self.long_tgt, self.long_trail,
                self.short_entry, self.short_tgt, self.short_trail]

    def prepare_orders(self):
        """
        Finalises the orders and transmits them to TWS
        :return:
        """
        if self.last_price <= 0:
            return

        # Update order ids, set parent order ids
        o = self.nextValidOrderId

        # Populate orders
        self.long_entry.orderId = str(o)
        self.long_entry.ocaGroup = "News trader"
        self.long_tgt.orderId = str(o + 1)
        self.long_tgt.parentId = str(self.long_entry.orderId)
        self.long_trail.orderId = str(o + 2)
        self.long_trail.parentId = str(self.long_entry.orderId)

        self.short_entry.orderId = str(o + 3)
        self.short_entry.ocaGroup = "News Trader"
        self.short_tgt.orderId = str(o + 4)
        self.short_tgt.parentId = str(self.short_entry.orderId)
        self.short_trail.orderId = str(o + 5)
        self.short_trail.parentId = str(self.short_entry.orderId)

    def wrapper_price_update(self, set_price):
        """
        Updates the prices of the order structure
        :param set_price:
        :return:
        """
        self.logger.log("Setting order structure around price " + str(set_price))
        self.set_price = set_price
        self.long_entry.lmtPrice = set_price + self.entry_spread
        self.long_entry.auxPrice = set_price + self.entry_spread
        self.long_tgt.lmtPrice = set_price + self.tgt_spread
        self.long_trail.trailStopPrice = set_price - self.trail_spread
        self.long_trail.lmtPriceOffset = self.trail_spread
        self.long_trail.auxPrice = self.trail_spread

        self.short_entry.lmtPrice = set_price - self.entry_spread
        self.short_entry.auxPrice = set_price - self.entry_spread
        self.short_tgt.lmtPrice = set_price - self.tgt_spread
        self.short_trail.trailStopPrice = set_price + self.trail_spread
        self.short_trail.lmtPriceOffset = self.trail_spread
        self.short_trail.auxPrice = self.trail_spread

    def tickPrice(self, req_id: TickerId, tick_type: TickType, price: float, attrib: TickAttrib):
        """
        Custom instrument price tick processing
        :param req_id:
        :param tick_type:
        :param price:
        :param attrib:
        :return:
        """
        # super().tickPrice(req_id, tick_type, price, attrib)
        # Here we just update the tick price, order adjustment is run in an
        # endless trader loop in a different thread. Scroll down to see the code.

        log_str = "Price tick " + str(tick_type) + " : " + str(price)
        if tick_type == TickTypeEnum.LAST:
            self.logger.log("Updating last price to " + str(price))
            self.last_price = price
        self.logger.verbose(log_str)

    def execDetails(self, req_id: int, contract: Contract, execution: Execution):
        """
        Execution details processing. Change trade status from HOT to ACTIVE and from
        ACTIVE to COLD, when either target or trail executes.
        :param req_id:
        :param contract:
        :param execution:
        :return:
        """
        self.logger.verbose("Execution details for req_id " + str(req_id))

    def execDetailsEnd(self, req_id: int):
        """
        End of execution details override
        :param req_id:
        :return:
        """
        self.logger.verbose("End of execution details for req_id " + str(req_id))

    def orderStatus(self, order_id: OrderId, status: str, filled: float,
                    remaining: float, avg_fill_price: float, perm_id: int,
                    parent_id: int, last_fill_price: float, client_id: int,
                    why_held: str, mkt_cap_price: float):
        """
        Order status processing for trader status changing
        :param order_id:
        :param status:
        :param filled:
        :param remaining:
        :param avg_fill_price:
        :param perm_id:
        :param parent_id:
        :param last_fill_price:
        :param client_id:
        :param why_held:
        :param mkt_cap_price:
        :return:
        """
        self.logger.log("Order " + str(order_id) + " status " + status +
                        " fill price " + str(avg_fill_price))
        # This part should be covered by OCA grouping on entry orders
        if order_id == self.long_entry.orderId or order_id == self.short_entry.orderId:
            self.status = TraderStatus.ACTIVE

        if order_id == self.long_trail.orderId or order_id == self.long_tgt.orderId:
            self.status = TraderStatus.COLD
            # Here we should add PnL calculation

        if order_id == self.short_trail.orderId or order_id == self.short_tgt.orderId:
            self.status = TraderStatus.COLD
            # Here we should add PnL calculation

    def error(self, req_id: TickerId, error_code: int, error_string: str):
        """
        TWS error reporting
        :param req_id:
        :param error_code:
        :param error_string:
        :return:
        """
        # super().error(req_id, error_code, error_string)
        self.logger.error(str(req_id) + ":" + str(error_code) + ":" + error_string)

    def get_last_price(self):
        """
        Returns last known price of the instrument
        :return: last price
        """
        return self.last_price

    def set_trader_status(self, status: TraderStatus):
        """
        Sets trader status in wrapper
        :param status:
        :return:
        """
        self.status = status

    def get_trader_status(self) -> TraderStatus:
        """
        Returns trader status
        :return:
        """
        return self.status


class Trader(TwsWrapper, TwsClient):
    """
    Main trader object for news trader
    """
    def __init__(self, symbol: str, expiry: str, sec_type: str, exchange: str, currency: str):
        """
        Simple constructor for the trader class
        """
        self.logger = Logger(LogLevel.normal, "Trader")
        self.logger.log("Trader init")

        TwsWrapper.__init__(self)
        TwsClient.__init__(self, wrapper=self)

        self.connect("localhost", 4001, 12)
        thread = Thread(target=self.run)
        thread.start()
        setattr(self, "_thread", thread)

        # Wait until we can do stuff
        while self.nextValidOrderId == -1:
            time.sleep(10)

        # Instrument to be traded.
        self.cont = Contract()
        self.inst = symbol
        self.exchange = exchange
        self.sec_type = sec_type
        self.expiry = expiry
        self.currency = currency

        # Bookkeeping
        self.entry_price = 0
        self.pnl = 0

    def print_pnl(self):
        """
        Prints out current PnL for the trader
        :return:
        """
        self.logger.log("Current PnL is: " + str(self.pnl))

    def update_order_prices(self):
        """
        Updates order prices to current market state
        :return:
        """
        self.logger.log("Updating order prices")
        self.wrapper_price_update(self.get_last_price())
        for i in self.get_orders():
            self.placeOrder(i.orderId, self.cont, i)

    def req_data(self):
        """
        Requests market data for the instrument
        :return:
        """
        self.cont.symbol = self.inst
        self.cont.exchange = self.exchange
        self.cont.secType = self.sec_type
        self.cont.currency = self.currency
        self.cont.lastTradeDateOrContractMonth = self.expiry

        self.logger.log("Requesting market data for the instrument")
        self.reqContractDetails(2, self.cont)
        self.reqMktData(3, self.cont, "", False, False, [])

    def place_orders(self):
        """
        Opens orders for both sides: entry, target and trail stop
        :return:
        """
        self.logger.log("Placing news trader orders")
        for i in self.get_orders():
            self.logger.log("Placing order " + str(i.orderId))
            self.placeOrder(i.orderId, self.cont, i)
        self.status = TraderStatus.HOT

    def trade(self):
        """
        Main trading loop
        :return: nothing
        """
        self.logger.log("Setting up orders")
        self.prepare_orders()
        self.wrapper_price_update(self.get_last_price())
        self.place_orders()
        self.logger.log("Entering main trading loop")

        adj_thread = Thread(target=self.update_loop)
        adj_thread.start()
        setattr(self, "_adj_thread", adj_thread)

        # TODO here we need to add endless loop for user input (ie. exit trader, change status)
        user_input = ""
        while user_input != "Q":
            user_input = input("News trader (Quit, Hot, Cold:").upper()
            if user_input == "H":
                # If cold, enter new orders, start updating prices
                if self.get_trader_status() == TraderStatus.COLD:
                    self.place_orders()
                    self.set_trader_status(TraderStatus.HOT)

                # Do nothing if we are active
                if self.get_trader_status() == TraderStatus.ACTIVE:
                    self.logger.error("We have active positions, will not change state!")

            if user_input == "C":
                # If we are active, show respective error message
                if self.get_trader_status() == TraderStatus.ACTIVE:
                    self.logger.error("Trader active, there are open positions!")

                # Cancel all open orders
                if self.get_trader_status() == TraderStatus.HOT or self.get_trader_status() == TraderStatus.ACTIVE:
                    self.cancelOrders()
                self.set_trader_status(TraderStatus.COLD)

        self.logger.log("Shutting down main trading loop")

    def cancel_orders(self):
        """
        Cancels all open orders
        :return:
        """
        for i in self.get_orders():
            self.cancelOrder(i.orderId)

    def update_loop(self):
        """
        Thread for updating the order structure
        :return:
        """
        while True:
            time.sleep(self.time_adjust / 1000)
            if self.status == TraderStatus.HOT and abs(self.set_price - self.last_price) > self.delta_adjust:
                self.wrapper_price_update(self.last_price)
                self.place_orders()

    def stop(self):
        """
        Stops all streaming data, cancels all orders
        Closes the TWS connection
        :return:
        """
        self.logger.log("Trader closing down")
        # If we have active orders, cancel them
        if self.status == TraderStatus.HOT:
            self.cancel_orders()

        # Stop market data
        self.cancelMktData(3)

        # Disconnect from the API
        self.disconnect()

        # Print out the final PnL:
        self.print_pnl()


def main():
    """
    Main trading code and entry point for the trader

    :return: nothing
    """
    logger = Logger(LogLevel.normal, "NewsTrader")
    logger.log("News trader init")

    trader = Trader("CL", "201812", "FUT", "NYMEX", "USD")
    trader.req_data()
    time.sleep(6)
    trader.trade()
    time.sleep(10)
    trader.stop()

    logger.log("News trader exiting")


# Main entry point for the news trader
if __name__ == "__main__":
    main()