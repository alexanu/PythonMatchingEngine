#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
:
Created on Thu May 16 14:14:51 2019


@author: Francisco Merlos
"""
from abc import ABC, abstractmethod
from datetime import datetime
from config.configuration_yaml import Configuration
from marketsimulator.prices_idx import get_band_dicts
import numpy as np
import pandas as pd
import pdb
import warnings

config = Configuration()
TICKER_BANDS = config.get_liq_bands()
DEFAULT_BAND = 'band6'
AVG_TRANSACTS = config.get_trades_bands()
PX_IDXS, PRICES, MAX_TICK = get_band_dicts([1, 2, 3, 4, 5, 6])
STATS = ['price', 'vol', 'agg_ord', 'pas_ord', 'buy_init', 'timestamp']
MY_STATS = ['price', 'vol', 'my_uid', 'timestamp']
TICK_SIZE_REGIME_URL = 'https://www.emissions-euets.com/tick-size-regime'


class Orderbook:
    def __init__(self, ticker, max_impact=20, resilience=1):
        if ticker not in TICKER_BANDS:
            band = DEFAULT_BAND
            warnings.warn(f'Ticker {ticker} not found in liquidity bands'
                           ' configuration file. \n Band6 (highest liquidity'
                           ' stock) will be set as default for tick size calc.\n'
                          f' Check {TICK_SIZE_REGIME_URL} for more info')
        else:
            band = TICKER_BANDS[ticker]
            
        #        self.band_ticks = self.__class__.band_ticks[band]
        self.band_idxs = PX_IDXS[band]
        self.band_prices = PRICES[band]
        self.max_tick = MAX_TICK[band]
        self.init_size = int(AVG_TRANSACTS[band])
        self.inc = int(max(0.1 * AVG_TRANSACTS[band], 10))
        self.low_inc = 10
        # default day
        self.def_day = datetime(1970, 1, 1)
        self.max_impact = max_impact
        self.resilience = resilience
        self._bids = Bids()
        self._asks = Asks()
        self.create_stats_dict()
        # keeps track of all orders sent to the orderbook
        # allows fast access of orders status by uid
        self._orders = dict()
        self.n_my_orders = 0
        self.ntrds = 0
        self.my_ntrds = 0
        self.cumvol = 0
        self.my_cumvol = 0
        self.cumturn = 0.
        self.my_cumturn = 0.
        self.market_impact = 0
        self.my_cumvol_sent = 0
        self.last_px = None

    def reset_ob(self, reset_all):

        if reset_all:
            self._bids = Bids()
            self._asks = Asks()
            self.create_stats_dict()
            self._orders = dict()

        self.n_my_orders = 0
        self.ntrds = 0
        self.my_ntrds = 0
        self.cumvol = 0
        self.my_cumvol = 0
        self.cumturn = 0.
        self.my_cumturn = 0.
        self.market_impact = 0

    def create_stats_dict(self, stat_dict=None):

        if stat_dict == 'trades' or stat_dict is None:
            self.trades = {
                key: np.zeros(self.inc)
                for key in STATS
            }
            self.trades['timestamp'] = np.full(self.inc,
                                               self.def_day)

        if stat_dict == 'last_trades' or stat_dict is None:
            self.last_trades = {
                key: np.zeros(self.low_inc)
                for key in STATS
            }
            self.last_trades['timestamp'] = np.full(self.low_inc,
                                                    self.def_day)

        if stat_dict == 'my_trades' or stat_dict is None:
            self.my_trades = {
                key: np.zeros(self.inc)
                for key in MY_STATS
            }
            self.my_trades['timestamp'] = np.full(self.inc,
                                                  self.def_day)

        if stat_dict == 'my_last_trades' or stat_dict is None:
            self.my_last_trades = {
                key: np.zeros(self.low_inc)
                for key in MY_STATS
            }
            self.my_last_trades['timestamp'] = np.full(self.low_inc,
                                                       self.def_day)

    def inc_dict_size(self, stat_dict, inc):

        # default array
        def_arr = np.zeros(inc)
        # default day
        def_day = np.full(inc, self.def_day)

        new_dict = {(key): (np.hstack([stat_dict[key], def_arr])
                            if key != 'timestamp' else np.hstack([stat_dict[key], def_day]))
                    for key in stat_dict.keys()
                    }

        return new_dict

    # Best Bid
    @property
    def bbid(self):
        if self._bids.best is None:
            return None
        else:
            return self._bids.best.price, self._bids.best.vol

    # Best ask
    @property
    def bask(self):
        if self._asks.best is None:
            return None
        else:
            return self._asks.best.price, self._asks.best.vol

    def compute_vwap(self, trades):

        return (np.sum(trades['price'] * trades['vol'])
                / np.sum(trades['vol']))

    @property
    def vwap(self):
        if self.trades:
            return self.compute_vwap(self.trades)
        else:
            return np.nan

    @property
    def my_vwap(self):
        if self.my_trades:
            return self.compute_vwap(self.my_trades)
        else:
            return np.nan

    @property
    def my_pov(self):
        if self.cumturn > 0:
            return self.my_cumvol / self.cumvol
        else:
            return 0

    @property
    def trades_vol(self):
        return self.trades['vol'][:self.ntrds]

    @property
    def trades_px(self):
        return self.trades['price'][:self.ntrds]

    @property
    def trades_time(self):
        return self.trades['timestamp'][:self.ntrds]

    @property
    def my_trades_vol(self):
        return self.my_trades['vol'][:self.my_ntrds]

    @property
    def my_trades_px(self):
        return self.my_trades['price'][:self.my_ntrds]

    @property
    def my_trades_time(self):
        return self.my_trades['timestamp'][:self.my_ntrds]

    def get(self, uid):
        """  Get orderbook order by uid
            
            Params:
                uid (int): unique identifier of the Order
        
            Returns:
                order (dict): a dictionary with the order info
        
        """
        order = self._orders[uid]
        return {'uid': order.uid,
                'is_buy': order.is_buy,
                'qty': order.qty,
                'cumqty': order.cumqty,
                'leavesqty': order.leavesqty,
                'price': order.price,
                'timestamp': order.timestamp,
                'active': order.active}

    def get_new_price(self, price, n_moves):
        """ Given a price and a number of ticks of offset (n_moves)
            it returns the new price 

            The tick size will depend on the price and the liquidity
            band of the stock.

            This function allows you to move a price a certain number
            of ticks without needing to know which is the tick size
            corresponding to the stock a this price.
            
        """

        try:
            return self.band_prices[self.band_idxs[price] + n_moves]
        except (KeyError, IndexError):
            if n_moves >= 0:
                try:
                    assert price < self.band_prices[-1]
                except AssertionError:
                    pdb.set_trace()
                return price + n_moves * self.max_tick
            else:
                if price > self.band_prices[-1]:
                    n_above = (price - self.band_prices[-1]) / self.max_tick

                    if abs(n_moves) > n_above:
                        return self.band_prices[n_moves + n_above]
                    else:
                        return price + n_moves * self.max_tick
                else:
                    if price == self.band_prices[0]:
                        return price
                    else:
                        raise ValueError(f'Price {price} not found')

    def send(self, is_buy, qty, price, uid,
             is_mine=False, timestamp=datetime.now()):
        """ Send new order to orderbook
            Passive orders can't be matched and will be added to the book
            Aggressive orders are matched against opp. side's resting order
            
            Args:
                is_buy (bool): True if it is a buy order
                qty (int): initial quantity or size of the order 
                price (float): limit price of the order
                uid (int): universal identifier of the order
                is_mine (bool): False if the order corresponds to a
                historical order instead of you own orders
                uid (int)
                timestamp (float): time of processing 
                
        """
        if np.isnan(price):
            raise Exception("Price cannot be nan. Use np.Inf in needed")

        if not is_mine:
            price = self._affect_price_with_market_impact(price)
        else:
            self.n_my_orders += 1
            self.my_cumvol_sent += qty

        neword = Order(uid, is_buy, qty, price, timestamp)
        self._orders.update({uid: neword})
        while (neword.leavesqty > 0):
            if self._is_aggressive(neword):
                self._sweep_best_price(neword)
            #                self.update_metrics(trdpx=exe_px,trdqty=exe_vol)
            else:
                if is_buy:
                    self._bids.add(neword)
                else:
                    self._asks.add(neword)
                return

    def _affect_price_with_market_impact(self, price):
        """ Modifies historical prices to be sent to the Orderbook by
            the cummulative effect of market impact that our own orders
            would have produced in a real trading session. 

            When we sweep a position in real life, this has an impact on
            the prices that the rest of the actors will be sending afterwards.
            We move the markets slightly with our orders.

        """
        if self.market_impact >= 1:
            nticks = min(int(self.resilience*self.market_impact),
                         self.max_impact)
            price = self.get_new_price(price=price, n_moves=nticks)
        elif self.market_impact <= -1:
            nticks = max(int(self.resilience*self.market_impact),
                         -1 * self.max_impact)
            price = self.get_new_price(price=price, n_moves=nticks)        
        return price

    def cancel(self, uid):

        """ Cancel order identified by its uid
        
        """
        order = self._orders[uid]

        if uid <  0:
            self.my_cumvol_sent -= order.leavesqty

        if order.active:

            if order.is_buy:
                pricelevel = self._bids.book[order.price]
            else:

                pricelevel = self._asks.book[order.price]

            # right side
            if order.next is None:
                pricelevel.tail = order.prev
                if order is pricelevel.head:
                    self._remove_price(order.is_buy, order.price)
                else:
                    order.prev.next = None
                    # left side
            elif order is pricelevel.head:
                pricelevel.head = order.next
                order.next.prev = None
            # middle
            else:
                order.next.prev = order.prev
                order.prev.next = order.next

            order._cumqty = order.qty - order.leavesqty
            order.leavesqty = 0
            order.active = False

        return

    def modif(self, uid, qty_down):
        """ Modify an order identified by its uid. 
        
        This transaction does not make the order lose its prite-time 
        priority in the queue, but has the limitation of only being
        able to downsize the order quantity. 
        
        For quantity increase or price modification, you need to cancel
        previous order and send a new one. 

        Args:
            uid (int): identifier of the order to be modified
            qty_down(int): quantity to substract to current order leavesqty
        
        """

        if uid in self._orders:
            prev_ord = self._orders[uid]
            qty_down = min(prev_ord.leavesqty, qty_down)
            prev_ord.leavesqty -= qty_down
            prev_ord.qty -= qty_down
            if uid < 0:
                self.my_cumvol_sent -= qty_down
            if prev_ord.leavesqty == 0:
                self.cancel(uid)

    def _is_aggressive(self, order):
        """ Aggressive orders are those that would be matched against
        resting orders in the book upon its arrival to the book. 
        
        Passive orders have a price that cannot result in immediate
        matching and would therefore rest in the orderbook increasing
        its liquidity. 
        
        Args:
            Order (Order): order to be checked for aggresiveness
            
        
        """

        is_agg = True
        if order.is_buy:
            if self._asks.best is None or self._asks.best.price > order.price:
                is_agg = False
        else:
            if self._bids.best is None or self._bids.best.price < order.price:
                is_agg = False
        return is_agg

    #    def update_metrics(self, trdpx, trdqty):
    #
    #        self.cumvol += trdqty
    #        self.cumefe += round(trdpx * trdqty, 3)
    #        self.obvwap = self.cumefe/self.cumvol

    def update_last_trades(self, stats, pos):

        for i in range(len(STATS)):

            try:
                self.last_trades[STATS[i]][pos] = stats[i]
            except IndexError:
                self.last_trades = self.inc_dict_size(self.last_trades,
                                                      inc=self.low_inc)
                self.last_trades[STATS[i]][pos] = stats[i]

    def update_my_last_trades(self, my_stats, pos):

        for i in range(len(MY_STATS)):

            try:
                self.my_last_trades[MY_STATS[i]][pos] = my_stats[i]
            except IndexError:
                self.my_last_trades = self.inc_dict_size(self.my_last_trades,
                                                         inc=self.low_inc)
                self.my_last_trades[MY_STATS[i]][pos] = my_stats[i]

    def update_trades(self, pos):

        end = self.ntrds + pos
        for stat in STATS:

            end = self.ntrds + pos
            if end < len(self.trades[stat]):
                self.trades[stat][self.ntrds:end
                ] = self.last_trades[stat][:pos]
            else:
                self.trades = self.inc_dict_size(self.trades,
                                                 inc=self.inc)
                self.trades[stat][self.ntrds:end
                ] = self.last_trades[stat][:pos]

        self.ntrds += pos

    def update_my_trades(self, pos):

        end = self.my_ntrds + pos
        for my_stat in MY_STATS:
            #            self.my_trades[my_stat] += self.my_last_trades[my_stat]
            if end < len(self.my_trades[my_stat]):
                self.my_trades[my_stat][self.my_ntrds:end
                ] = self.my_last_trades[my_stat][:pos]
            else:
                self.my_trades = self.inc_dict_size(self.my_trades,
                                                    inc=self.inc)
                self.my_trades[my_stat][self.my_ntrds:end
                ] = self.my_last_trades[my_stat][:pos]

        self.my_ntrds += pos

    def _sweep_best_price(self, order):
        """ Match Order against opposite side of the orderbook, 
        removing liquidity and generating the corresponding trades. 
        
        Args:
            order (order): order to be matched against the opp. side book
        
        """

        # TODO: Think of a different aggression effect

        my_agg_vol = 0
        ob_agg_vol = 0
        n_newtrd = 0
        n_my_newtrd = 0
        self.create_stats_dict(stat_dict='last_trades')
        restart_my_last_trades = True
        my_trade = False
        breaking = False

        if order.is_buy:
            best = self._asks.best
            agg_effect_side = 1
        else:
            best = self._bids.best
            agg_effect_side = -1

        init_best_vol = best.head.leavesqty

        assert order.leavesqty > 0
        while order.leavesqty > 0:

            if best.head.leavesqty <= order.leavesqty:
                trdqty = best.head.leavesqty
                best.head.leavesqty = 0

                if best.head.uid < 0:
                    my_trade = True
                    my_uid = best.head.uid
                elif order.uid < 0:
                    my_trade = True
                    my_agg_vol += trdqty
                    my_uid = order.uid
                else:
                    my_trade = False
                    ob_agg_vol += trdqty

                price = best.price
                best_uid = best.head.uid

                best.pop()
                order.leavesqty -= trdqty
                if best.head is None:
                    # remove PriceLevel from the order's opposite side
                    self._remove_price(not order.is_buy, best.price)
                    breaking = True
            else:
                trdqty = order.leavesqty
                if best.head.uid < 0:
                    my_trade = True
                    my_uid = best.head.uid
                elif order.uid < 0:
                    my_trade = True
                    my_agg_vol += trdqty
                    my_uid = order.uid
                else:
                    my_trade = False
                    ob_agg_vol += trdqty

                price = best.price
                best_uid = best.head.uid

                best.head.leavesqty -= order.leavesqty
                order.leavesqty = 0

            if price == np.inf:
                pdb.set_trace()

            turn = trdqty * price
            self.cumvol += trdqty
            self.cumturn += turn
            stats = [price, trdqty, order.uid, best_uid,
                     order.is_buy, order.timestamp]
            self.update_last_trades(stats=stats, pos=n_newtrd)
            n_newtrd += 1

            if my_trade:
                self.my_cumvol += trdqty
                self.my_cumturn += turn
                if restart_my_last_trades:
                    self.create_stats_dict(stat_dict='my_last_trades')
                    restart_my_last_trades = False
                my_stats = [price, trdqty, my_uid, order.timestamp]
                self.update_my_last_trades(my_stats, pos=n_my_newtrd)
                n_my_newtrd += 1
                my_trade = False

            if breaking:
                break

        self.update_trades(pos=n_newtrd)
        if not restart_my_last_trades:
            self.update_my_trades(pos=n_my_newtrd)

        if my_agg_vol > 0:
            agg_effect = min(1., my_agg_vol / init_best_vol)
            self.market_impact += (agg_effect * agg_effect_side)

        if ob_agg_vol > 0:
            ob_correction = False
            if (self.market_impact > 0) and (agg_effect_side == -1):
                ob_correction = True
            elif (self.market_impact < 0) and (agg_effect_side == 1):
                ob_correction = True
            if ob_correction:
                agg_effect = min(1., ob_agg_vol / init_best_vol)
                pov_f = 1 - self.my_cumvol / self.cumvol
                self.market_impact += (agg_effect * agg_effect_side) * pov_f

        self.last_px = price

        return

    def _remove_price(self, is_buy, price):
        """ Remove a PriceLevel from the book
        
        Args:
            is_buy (bool): True to remove a PriceLevel from the Bids
        
        """

        if is_buy:
            del self._bids.book[price]
            if len(self._bids.book) > 0:
                self._bids.best = self._bids.book[max(self._bids.book.keys())]
            else:
                self._bids.best = None
        else:
            del self._asks.book[price]
            if len(self._asks.book) > 0:
                self._asks.best = self._asks.book[min(self._asks.book.keys())]
            else:
                self._asks.best = None

    def top_bidpx(self, nlevels):
        """ Returns the first nlevels of the Bids ordered by price desc
        
        Args:
            nlevels (int): number of price levels to return
        Returns:
            the first nlevels of the Bids ordered by price desc
        """

        pbids = nlevels * [np.nan]

        try:
            bbid = self._bids.best.price
        except:
            return pbids

        next_bbidpx = bbid
        pbids[0] = next_bbidpx
        n_px = min(nlevels, len(self._bids.book))
        px_found = 1

        while px_found < n_px:
            nextpx = self.get_new_price(next_bbidpx, -1)
            next_bbidpx = nextpx
            if next_bbidpx in self._bids.book:
                pbids[px_found] = nextpx
                px_found += 1
            else:
                continue

        return pbids

    def top_askpx(self, nlevels):
        """ Returns the first nlevels of the Ask ordered by price asc
        
        Args:
            nlevels (int): number of price levels to return
            
        Returns:
            first nlevels of the Ask ordered by price asc
        """

        pasks = nlevels * [np.nan]
        try:
            bask = self._asks.best.price
        except:
            return pasks

        next_baskpx = bask
        pasks[0] = next_baskpx
        n_px = min(nlevels, len(self._asks.book))
        px_found = 1

        while px_found < n_px:
            nextpx = self.get_new_price(next_baskpx, 1)
            next_baskpx = nextpx
            if next_baskpx in self._asks.book:
                pasks[px_found] = nextpx
                px_found += 1
            else:
                continue
        return pasks

    def top_bids_cumvol(self, nlevels):

        nlvl_vol = 0

        try:
            bbid = self._bids.best.price
        except:
            return nlvl_vol, None

        nlvl_vol += self._bids.book[bbid].vol
        next_bbidpx = bbid
        n_px = min(nlevels, len(self._bids.book))
        px_found = 1

        while px_found < n_px:
            nextpx = self.get_new_price(next_bbidpx, -1)
            next_bbidpx = nextpx

            try:
                nlvl_vol += self._bids.book[next_bbidpx].vol
                px_found += 1
            except KeyError:
                continue

        return nlvl_vol, next_bbidpx

    def top_asks_cumvol(self, nlevels):

        nlvl_vol = 0

        try:
            bask = self._asks.best.price
        except:
            return nlvl_vol, None

        nlvl_vol += self._asks.book[bask].vol
        next_baskpx = bask
        n_px = min(nlevels, len(self._asks.book))
        px_found = 1

        while px_found < n_px:
            nextpx = self.get_new_price(next_baskpx, 1)
            next_baskpx = nextpx

            try:
                nlvl_vol += self._asks.book[next_baskpx].vol
                px_found += 1
            except KeyError:
                continue

        return nlvl_vol, next_baskpx


    def top_bids(self, nlevels):
        """ Returns the first nlevels best bids of the book, including
        both price and volume in price desc order
        
        Args:
            nlevels (int): number of price levels to return
        Returns: 
            the first nlevels best bids of the book, including
            both price and volume in price desc order
        
        """
        pbids = nlevels * [np.nan]
        vbids = nlevels * [np.nan]
        try:
            bbid = self._bids.best.price
        except:
            return [pbids, vbids]

        vbids[0] = self._bids.book[bbid].vol
        next_bbidpx = bbid
        pbids[0] = next_bbidpx
        n_px = min(nlevels, len(self._bids.book))
        px_found = 1

        while px_found < n_px:
            nextpx = self.get_new_price(next_bbidpx, -1)
            next_bbidpx = nextpx
            try:
                vbids[px_found] = self._bids.book[nextpx].vol
                pbids[px_found] = nextpx
                px_found += 1
            except KeyError:
                continue

        return [pbids, vbids]

    def top_asks(self, nlevels):
        """ Returns the first nlevels best asks of the book, including
        both price and volume in price asc order
        
        Args:
            nlevels (int): number of price levels to return
        Returns: 
            the first nlevels best asks of the book, including
            both price and volume in price asc order
        
        """

        pasks = nlevels * [np.nan]
        vasks = nlevels * [np.nan]
        try:
            bask = self._asks.best.price
        except:
            return [pasks, vasks]

        vasks[0] = self._asks.book[bask].vol
        next_baskpx = bask
        pasks[0] = next_baskpx
        n_px = min(nlevels, len(self._asks.book))
        px_found = 1

        while px_found < n_px:
            nextpx = self.get_new_price(next_baskpx, 1)
            next_baskpx = nextpx
            try:
                vasks[px_found] = self._asks.book[nextpx].vol
                pasks[px_found] = nextpx
                px_found += 1
            except KeyError:
                continue

        return [pasks, vasks]

    def __str__(self):
        pbid, vbid = self.top_bids(10)
        pask, vask = self.top_asks(10)
        df = pd.DataFrame({'vbid': vbid, 'pbid': pbid, 'pask': pask, 'vask': vask})
        return str(df)


class Order:
    """ Represents an order inside the orderbook with its current status 
    
    """

    # __slots__ = ["uid", "is_buy", "qty", "price", "timestamp", "status"]

    def __init__(self, uid, is_buy, qty, price, timestamp=datetime.now()):
        self.uid = uid
        self.is_buy = is_buy
        self.qty = qty
        # outstanding volume in orderbook. If filled or canceled => 0. 
        self.leavesqty = qty
        # You should not access _cumqty directly.
        # Use cumqty property instead
        self._cumqty = None
        self.price = price
        self.timestamp = timestamp
        # is the order active and resting in the orderbook?
        self.active = False
        # DDL attributes import unittest
        self.prev = None
        self.next = None

    @property
    def cumqty(self):
        if self._cumqty:
            return self._cumqty
        else:
            return self.qty - self.leavesqty


class PriceLevel:
    """ Represents a price in the orderbook with its order queue
    
    """

    def __init__(self, order):
        self.price = order.price
        self.head = order
        self.tail = order

    # Cummulative volume of all orders at this PriceLevel
    @property
    def vol(self):
        vol = 0
        next_order = self.head
        while next_order is not None:
            vol += next_order.leavesqty
            next_order = next_order.next
        return vol

    def append(self, order):
        self.tail.next = order
        order.prev = self.tail
        self.tail = order

    def pop(self):
        self.head.active = False
        if self.head.next is None:
            self.head = None
            self.tail = None
        else:
            self.head.next.prev = None
            self.head = self.head.next


class HalfBook(ABC):
    """ Abstract class representing the common properties of a half orderbook.
    Bids or Asks half orderbooks that inherit from it 
    will have different is_new_best methods    
    """

    def __init__(self):
        self.book = dict()
        # Pointer to Best PriceLevel 
        self.best = None

    def add(self, order):
        if order.price in self.book:
            self.book[order.price].append(order)
        else:
            new_pricelevel = PriceLevel(order)
            self.book.update({order.price: new_pricelevel})
            if self.best is None or self.is_new_best(order):
                self.best = new_pricelevel
        order.active = True

    @abstractmethod
    def is_new_best(self, order):
        pass


class Bids(HalfBook):
    """ Bids Orderbook where best PriceLevel has highest price
        Implements is_new_best abstract method that behaves differently
        for Bids or Asks
    """

    def __init__(self):
        super().__init__()

    def is_new_best(self, order):
        if order.price > self.best.price:
            return True
        else:
            return False


class Asks(HalfBook):
    """ Asks Orderbook where best PriceLevel has lowest price
        Implements is_new_best abstract method that behaves differently
        for Bids or Asks
    """

    def __init__(self):
        super().__init__()

    def is_new_best(self, order):
        if order.price < self.best.price:
            return True
        else:
            return False
