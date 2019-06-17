#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Jun 15 22:32:03 2019

@author: paco
"""

import numpy as np
from collections import deque

class BuyTheBid():

    
    def __init__(self, care_vol, child_vol):
        self.child_vol = child_vol
        self.care_leave = care_vol
        self.leave_uid = None
        self.done = False


    def send_new_child(self, gtw):
        new_qty = min(self.child_vol, self.care_leave)                    
        self.leave_uid = gtw.queue_my_new(is_buy=True,
                                    qty=new_qty,
                                    price=gtw.mkt.bbid[0])
        
        
    def eval_and_act(self, gtw):
                        
        if self.leave_uid is None:
            self.send_new_child(gtw)
        else:
            try:            
                leave_ord = gtw.ord_status(self.leave_uid)
            except KeyError:
                return
            
            # if my prev child order is filled
            if leave_ord['leavesqty'] == 0:
                # and the care is not totally filled
                if self.care_leave > 0:
                    self.send_new_child(gtw)
                else:
                    self.done = True
            # if not in best bid, modif price
            elif leave_ord['price'] != gtw.mkt.bbid[0]:                
                gtw.queue_my_cancel(uid=self.leave_uid)
                self.send_new_child(gtw)


    

class Pegged():
    
    def __init__(self, is_buy, lmtpx, qty, anchor_lvl,
                 offset, gtw, quick=False, max_jump=np.Inf):
        self.is_buy = is_buy    
        self.lmtpx = lmtpx
        self.qty = qty
        self.anchor_lvl = anchor_lvl
        self.offset = offset
        self.quick = quick
        self.max_jump = max_jump
        self.done = False
        self.jumps = 0
        
        # send order
        self.uid = gtw.queue_my_new(is_buy=is_buy,
                                    qty=qty,
                                    price=self._target_px(gtw))        
        
        
    def _target_px(self, gtw):
        
        # check which price we will follow
        if self.is_buy:
            anchor_px = gtw.mkt.top_bidpx(self.anchor_lvl)[self.anchor_lvl-1]
        else:
            anchor_px = gtw.mkt.top_askpx(self.anchor_lvl)[self.anchor_lvl-1]
        
        # add corresponding offset in ticks                 
        pegged_px = gtw.mkt.get_new_price(anchor_px, self.offset)
        
        # limit price
        if self.is_buy:
            target_px = min(pegged_px, self.lmtpx)
        else:
            target_px = max(pegged_px, self.lmtpx)
        
        return target_px
        
    
    def eval_and_act(self, gtw):
        
        # If checking it before it arrives to the market
        try:
            leave_ord = gtw.ord_status(self.uid)
        except KeyError:
            return
        
        if leave_ord['leavesqty'] == 0:
            self.done = True       
            return
        else:
            if self.jumps >= self.max_jump:
                return
            target_px = self._target_px(gtw)
            if self.quick:
                if self.is_buy:
                    if leave_ord['price'] >= target_px:
                        return
                else:
                    if leave_ord['price'] <= target_px:
                        return
                
            else:
                if leave_ord['price'] == target_px:
                    return
                
            gtw.queue_my_cancel(uid=self.uid)
            self.uid = gtw.queue_my_new(is_buy=self.is_buy,
                                    qty=self.qty,
                                    price=target_px)        
        
    


class SimplePOV():


    def __init__(self, is_buy, target_pov, lmtpx, qty, sweep_max):
        self.is_buy = is_buy
        self.target_pov = target_pov
        self.lmtpx = lmtpx
        self.qty = qty
        self.cumqty = 0
        self.pov = 0.
        self.sweep_max = sweep_max
        self.done = False
                

    def _target_px(self, gtw):
        if self.is_buy:
            max_px = gtw.mkt.get_new_price(gtw.mkt.bask[0], self.sweep_max)
            target_px = min(self.lmtpx, max_px)
        else:
            min_px = gtw.mkt.get_new_price(gtw.mkt.bbid[0], -self.sweep_max)            
            target_px = max(self.lmtpx, min_px)
        return target_px
        

    def eval_and_act(self, gtw):                    
        
        if gtw.mkt.my_cumvol >= self.qty:
            self.done = True
            return
        
        if gtw.mkt.my_pov < self.target_pov:
            target_vol = int(gtw.mkt.cumvol * self.target_pov) - gtw.mkt.my_cumvol
            next_vol = min(self.qty-gtw.mkt.my_cumvol, target_vol)            
            gtw.queue_my_new(is_buy=self.is_buy,
                            qty=next_vol,
                            price=self._target_px(gtw))        
        
    
        




#class POV():
#    def __init__(self, target_pov, lmtpx, qty, min_child):
#        self.target_pov = target_pov
#from gateway import Gateway
#from algorithms import BuyTheBid, SimplePOV
#        self.lmtpx = lmtpx
#        self.qty = qty
#        self.leaves_qty = qty
#        self.pov = 0
#        self.min_child = min_child
        
    
        
        
        
        